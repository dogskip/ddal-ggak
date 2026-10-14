"""Real process groups must finish on cancellation, timeout and excessive output."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import time
from pathlib import Path

import pytest

from ddk.adapters.preview import PreviewStartError
from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is required")
_LIMIT = 10 * 1024 * 1024


def _tree_script(marker: Path, *, parent_exits: bool = False) -> str:
    grandchild = "setInterval(() => {}, 1000)"
    child = (
        "const cp = require('child_process');"
        f"const child = cp.spawn(process.execPath, ['-e', {json.dumps(grandchild)}],"
        "{stdio: 'inherit'});"
        f"require('fs').writeFileSync({json.dumps(str(marker))}, "
        "JSON.stringify([process.ppid, process.pid, child.pid]));"
        "setInterval(() => {}, 1000)"
    )
    return (
        "const cp = require('child_process');"
        f"cp.spawn(process.execPath, ['-e', {json.dumps(child)}], {{stdio: 'inherit'}});"
        + (
            "setTimeout(() => process.exit(0), 300)"
            if parent_exits
            else "setInterval(() => {}, 1000)"
        )
    )


async def _pids(marker: Path) -> list[int]:
    async with asyncio.timeout(5):
        while not marker.exists():
            await asyncio.sleep(0.01)
    return json.loads(marker.read_text())


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def _assert_gone(pids: list[int]) -> None:
    async with asyncio.timeout(3):
        while any(_alive(pid) for pid in pids):
            await asyncio.sleep(0.02)


def _clean_test_group(pids: list[int]) -> None:
    if pids:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pids[0], signal.SIGKILL)


async def test_build_cancellation_reaps_owned_descendants_and_propagates(tmp_path: Path) -> None:
    marker = tmp_path / "pids.json"
    task = asyncio.create_task(
        SubprocessBuildRunner().run(["node", "-e", _tree_script(marker)], tmp_path)
    )
    pids = await _pids(marker)
    started = time.monotonic_ns()
    try:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (time.monotonic_ns() - started) / 1e9 < 2
        await _assert_gone(pids)
    finally:
        _clean_test_group(pids)


async def test_build_timeout_reaps_descendants_after_the_leader_exits(tmp_path: Path) -> None:
    marker = tmp_path / "pids.json"
    task = asyncio.create_task(
        SubprocessBuildRunner().run(
            ["node", "-e", _tree_script(marker, parent_exits=True)], tmp_path, timeout=1
        )
    )
    pids = await _pids(marker)
    try:
        async with asyncio.timeout(3):
            result = await task
        assert result.returncode == 124
        assert 900 <= result.duration_ms < 3000
        await _assert_gone(pids)
    finally:
        _clean_test_group(pids)


async def test_build_combined_output_is_bounded_and_fails_closed(tmp_path: Path) -> None:
    script = (
        "process.stdout.write(Buffer.alloc(6 * 1024 * 1024, 'a'));"
        "process.stderr.write(Buffer.alloc(6 * 1024 * 1024, 'b'))"
    )
    result = await SubprocessBuildRunner().run(["node", "-e", script], tmp_path)

    assert not result.success
    assert result.returncode == 125
    assert len(result.stdout.encode()) + len(result.stderr.encode()) <= _LIMIT
    assert "output limit" in result.stderr.lower()


@pytest.mark.parametrize("cancel", [False, True])
async def test_preview_start_failure_reaps_owned_descendants(tmp_path: Path, cancel: bool) -> None:
    marker = tmp_path / "pids.json"
    task = asyncio.create_task(
        SubprocessPreviewLauncher().start(
            ["node", "-e", _tree_script(marker, parent_exits=not cancel)],
            tmp_path,
            timeout_s=0.8,
        )
    )
    pids = await _pids(marker)
    try:
        if cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(PreviewStartError):
                await task
        await _assert_gone(pids)
    finally:
        _clean_test_group(pids)


async def test_preview_excessive_output_fails_before_start_timeout(tmp_path: Path) -> None:
    script = "process.stdout.write(Buffer.alloc(11 * 1024 * 1024)); setInterval(() => {}, 1000)"
    with pytest.raises(PreviewStartError, match="output limit"):
        await SubprocessPreviewLauncher().start(["node", "-e", script], tmp_path, timeout_s=0.8)


async def test_cleanup_failure_is_bounded_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    monkeypatch.setattr("ddk.adapters.subprocess_build_runner.CLEANUP_TIMEOUT_S", 0.05)
    process = MagicMock()
    process.pid = 4242
    process.returncode = None
    process.stdout = asyncio.StreamReader()
    process.stderr = asyncio.StreamReader()
    process.stdout.feed_eof()
    process.stderr.feed_eof()

    async def never_finishes() -> int:
        await asyncio.Event().wait()
        return 0

    process.wait = AsyncMock(side_effect=never_finishes)
    started = time.monotonic_ns()
    with (
        patch("asyncio.create_subprocess_exec", return_value=process),
        patch("os.killpg"),
    ):
        result = await SubprocessBuildRunner().run(["node", "-e", ""], tmp_path, timeout=0)
    await asyncio.sleep(0)

    assert (time.monotonic_ns() - started) / 1e9 < 0.5
    assert not result.success and result.returncode == 125
    assert "cleanup timed out" in result.stderr
    assert result.duration_ms >= 40
    process._transport.close.assert_called_once()


async def test_wall_clock_adjustment_does_not_change_timeout_or_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wall_times = iter([10**12, -(10**12)] * 100)
    monkeypatch.setattr(time, "time", lambda: next(wall_times))
    result = await SubprocessBuildRunner().run(
        ["node", "-e", "setInterval(() => {}, 1000)"], tmp_path, timeout=1
    )

    assert result.returncode == 124
    assert 900 <= result.duration_ms < 3000


async def test_preview_output_limit_still_applies_after_it_is_listening(tmp_path: Path) -> None:
    script = (
        "require('http').createServer((q,r) => r.end('ok'))"
        ".listen(Number(process.argv[1]), '127.0.0.1');"
        "setTimeout(() => {"
        "process.stdout.write(Buffer.alloc(6 * 1024 * 1024));"
        "process.stderr.write(Buffer.alloc(6 * 1024 * 1024));"
        "}, 400)"
    )
    session = await SubprocessPreviewLauncher().start(
        ["node", "-e", script, "{port}"], tmp_path, timeout_s=3
    )
    try:
        await asyncio.wait_for(session._output.exceeded.wait(), timeout=3)
        with pytest.raises(PreviewStartError, match="output limit"):
            await session.stop()
        assert len(session._output.stdout) + len(session._output.stderr) <= _LIMIT
        assert session._process.returncode is not None
    finally:
        await session.stop()


@pytest.mark.parametrize("preview", [False, True])
@pytest.mark.parametrize("cancel_twice", [False, True])
async def test_cancellation_during_process_creation_preserves_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preview: bool, cancel_twice: bool
) -> None:
    marker = tmp_path / "pids.json"
    original = asyncio.create_subprocess_exec

    async def delayed(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        process = await original(*args, **kwargs)
        await asyncio.sleep(0.2)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", delayed)
    command = ["node", "-e", _tree_script(marker)]
    if preview:
        task = asyncio.create_task(SubprocessPreviewLauncher().start(command, tmp_path))
    else:
        task = asyncio.create_task(SubprocessBuildRunner().run(command, tmp_path))
    pids = await _pids(marker)
    try:
        task.cancel()
        if cancel_twice:
            await asyncio.sleep(0.01)
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await _assert_gone(pids)
    finally:
        _clean_test_group(pids)

"""SubprocessBuildRunner: missing tools, runaway process trees, colour-free output."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner


@pytest.fixture(autouse=True)
def mocked_process_group() -> object:
    with patch("os.killpg"):
        yield


def _process(*, pid: int = 4242, returncode: int = 0) -> MagicMock:
    process = MagicMock()
    process.pid = pid
    process.returncode = returncode
    process.stdout = asyncio.StreamReader()
    process.stderr = asyncio.StreamReader()
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    process.wait = AsyncMock(return_value=returncode)
    return process


async def test_missing_executable_is_reported_as_exit_127(tmp_path: Path) -> None:
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("npm")):
        result = await SubprocessBuildRunner().run(["npm", "run", "build"], cwd=tmp_path)

    assert result.returncode == 127
    assert result.success is False
    assert "not found" in result.stderr.lower()


async def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    process = _process()
    process.stdout = asyncio.StreamReader()

    with (
        patch("asyncio.create_subprocess_exec", return_value=process),
        patch("os.killpg", side_effect=lambda *_: process.stdout.feed_eof()) as killpg,
    ):
        result = await SubprocessBuildRunner().run(["npm", "run", "build"], cwd=tmp_path, timeout=1)

    killpg.assert_called_once_with(4242, signal.SIGKILL)
    assert result.returncode == 124


async def test_child_leads_its_own_session_so_it_can_be_killed_as_a_group(
    tmp_path: Path,
) -> None:
    with patch("asyncio.create_subprocess_exec", return_value=_process()) as spawn:
        await SubprocessBuildRunner().run(["npm", "run", "build"], cwd=tmp_path)

    assert spawn.call_args.kwargs["start_new_session"] is True


async def test_child_output_is_requested_without_colour(tmp_path: Path) -> None:
    with patch("asyncio.create_subprocess_exec", return_value=_process()) as spawn:
        await SubprocessBuildRunner().run(["npm", "run", "build"], cwd=tmp_path)

    assert spawn.call_args.kwargs["env"]["NO_COLOR"] == "1"

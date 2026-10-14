"""Tests for SubprocessBuildRunner."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner


@pytest.fixture(autouse=True)
def mocked_process_group() -> object:
    with patch("os.killpg"):
        yield


def _process(stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> MagicMock:
    process = MagicMock()
    process.pid = 4242
    process.returncode = code
    process.stdout = asyncio.StreamReader()
    process.stderr = asyncio.StreamReader()
    process.stdout.feed_data(stdout)
    process.stderr.feed_data(stderr)
    process.stdout.feed_eof()
    process.stderr.feed_eof()
    process.wait = AsyncMock(return_value=code)
    return process


class TestSubprocessBuildRunner:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        mock_proc = _process(b"ok\n")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            runner = SubprocessBuildRunner()
            result = await runner.run(
                command=["npm", "run", "build"],
                cwd=Path("/tmp/test"),
            )

        assert result.success is True
        assert result.returncode == 0
        assert "ok" in result.stdout

    @pytest.mark.asyncio
    async def test_failure(self) -> None:
        mock_proc = _process(stderr=b"error\n", code=1)

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            runner = SubprocessBuildRunner()
            result = await runner.run(
                command=["npm", "run", "build"],
                cwd=Path("/tmp/test"),
            )

        assert result.success is False
        assert result.returncode == 1

    @pytest.mark.asyncio
    async def test_timeout_returns_124(self) -> None:
        mock_proc = _process()
        mock_proc.stdout = asyncio.StreamReader()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            patch("os.killpg", side_effect=lambda *_: mock_proc.stdout.feed_eof()),
        ):
            runner = SubprocessBuildRunner()
            result = await runner.run(
                command=["npm", "run", "build"],
                cwd=Path("/tmp/test"),
                timeout=1,
            )

        assert result.returncode == 124
        assert result.success is False

    @pytest.mark.asyncio
    async def test_rejects_commands_outside_the_sandbox_allowlist(self, tmp_path: Path) -> None:
        runner = SubprocessBuildRunner()

        with patch("asyncio.create_subprocess_exec") as create_process:
            result = await runner.run(["curl", "https://example.com"], cwd=tmp_path)

        assert result.returncode == 126
        assert "not allowed" in result.stderr.lower()
        create_process.assert_not_called()

    @pytest.mark.asyncio
    async def test_filters_secrets_and_rehomes_subprocess(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PATH", "/usr/bin")
        monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "must-not-leak")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-leak")
        monkeypatch.setenv("HOME", "/host/home")
        mock_proc = _process(b"ok\n")

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ) as create_process:
            await SubprocessBuildRunner().run(["npm", "--version"], cwd=tmp_path)

        child_env = create_process.call_args.kwargs["env"]
        assert child_env["PATH"] == "/usr/bin"
        assert child_env["HOME"] == str(tmp_path / ".ddk-home")
        assert child_env["npm_config_cache"] == str(tmp_path / ".ddk-home" / ".npm-cache")
        assert "DDK_ANTHROPIC_API_KEY" not in child_env
        assert "AWS_SECRET_ACCESS_KEY" not in child_env

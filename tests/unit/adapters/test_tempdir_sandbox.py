"""Tests for TempDirSandbox — policy enforcement and run_command."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.adapters.sandbox.policy import (
    ALLOWED_COMMANDS,
    ENV_WHITELIST,
    is_command_allowed,
    is_env_allowed,
    is_path_forbidden,
)
from ddk.adapters.sandbox.tempdir import TempDirSandbox


class TestSandboxPolicy:
    def test_allowed_commands_exist(self) -> None:
        assert "npm" in ALLOWED_COMMANDS
        assert "node" in ALLOWED_COMMANDS
        assert "git" in ALLOWED_COMMANDS

    def test_env_whitelist_exists(self) -> None:
        assert "PATH" in ENV_WHITELIST
        assert "HOME" in ENV_WHITELIST
        assert "NODE_ENV" in ENV_WHITELIST

    def test_is_command_allowed_true(self) -> None:
        assert is_command_allowed("npm") is True
        assert is_command_allowed("node") is True

    def test_is_command_allowed_false(self) -> None:
        assert is_command_allowed("rm") is False
        assert is_command_allowed("curl") is False

    def test_is_env_allowed_true(self) -> None:
        assert is_env_allowed("PATH") is True

    def test_is_env_allowed_false(self) -> None:
        assert is_env_allowed("AWS_SECRET_KEY") is False

    def test_is_path_forbidden(self) -> None:
        assert is_path_forbidden("/etc/passwd") is True
        assert is_path_forbidden("/tmp/safe") is False


class TestTempDirSandbox:
    @pytest.mark.asyncio
    async def test_create_and_cleanup(self, tmp_path: Path) -> None:
        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=tmp_path)
        assert work_dir.exists()
        await sandbox.cleanup()
        assert not work_dir.exists()

    @pytest.mark.asyncio
    async def test_create_does_not_import_external_symlink_targets(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        external = tmp_path / "external-secret.txt"
        external.write_text("secret", encoding="utf-8")
        (source / "linked-secret.txt").symlink_to(external)

        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=source)

        assert not (work_dir / "linked-secret.txt").exists()
        assert not (work_dir / "linked-secret.txt").is_symlink()
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_create_preserves_safe_relative_internal_symlinks(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        (source / "target.txt").write_text("ok", encoding="utf-8")
        (source / "link.txt").symlink_to("target.txt")

        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=source)

        assert (work_dir / "link.txt").is_symlink()
        assert (work_dir / "link.txt").read_text(encoding="utf-8") == "ok"
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_disallowed_command_returns_126(self, tmp_path: Path) -> None:
        sandbox = TempDirSandbox()
        await sandbox.create(source_path=tmp_path)

        result = await sandbox.run_command(["curl", "http://evil.com"])
        assert result.returncode == 126

        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_allowed_command_executes(self, tmp_path: Path) -> None:
        sandbox = TempDirSandbox()
        await sandbox.create(source_path=tmp_path)

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ok\n", b""))
        mock_proc.returncode = 0

        with patch(
            "asyncio.create_subprocess_exec",
            return_value=mock_proc,
        ):
            result = await sandbox.run_command(["node", "--version"])

        assert result.returncode == 0
        await sandbox.cleanup()


class TestSandboxCopyExclusions:
    @staticmethod
    def _seed(source: Path) -> None:
        for name, content in {
            "package.json": "{}",
            ".git/HEAD": "ref: refs/heads/main",
            ".ddk/cases/C-001/report.json": "{}",
            ".ddk-home/.npm-cache/x": "cache",
            ".env": "API_KEY=secret",
            ".env.local": "API_KEY=secret",
            ".env.example": "API_KEY=",
            "keys/server.pem": "-----BEGIN-----",
            "dist/index.js": "built",
            "src/dist/util.ts": "export {}",
            "node_modules/react/index.js": "module.exports = {}",
        }.items():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")

    @pytest.mark.asyncio
    async def test_history_workspace_and_caches_are_not_copied(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        self._seed(source)

        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=source)

        assert not (work_dir / ".git").exists()
        assert not (work_dir / ".ddk").exists()
        assert not (work_dir / ".ddk-home").exists()
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_secret_files_stay_out_but_env_templates_come_along(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        self._seed(source)

        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=source)

        assert not (work_dir / ".env").exists()
        assert not (work_dir / ".env.local").exists()
        assert not (work_dir / "keys" / "server.pem").exists()
        assert (work_dir / ".env.example").exists()
        await sandbox.cleanup()

    @pytest.mark.asyncio
    async def test_only_top_level_build_output_is_dropped(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        self._seed(source)

        sandbox = TempDirSandbox()
        work_dir = await sandbox.create(source_path=source)

        assert not (work_dir / "dist").exists()
        assert (work_dir / "src" / "dist" / "util.ts").exists()
        assert (work_dir / "node_modules" / "react" / "index.js").exists()
        assert (work_dir / "package.json").exists()
        await sandbox.cleanup()

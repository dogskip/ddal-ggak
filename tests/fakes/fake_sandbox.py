"""TempDirSandbox — uses tempfile.mkdtemp() instead of git worktree."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ddk.adapters.sandbox.base import CommandResult


class TempDirSandbox:
    """Uses tempfile.mkdtemp() instead of git worktree. Real file I/O."""

    def __init__(self) -> None:
        self._sandbox_path: Path | None = None

    async def create(self, source_path: Path) -> Path:
        self._sandbox_path = Path(tempfile.mkdtemp(prefix="ddk-sandbox-"))
        # Copy source files to sandbox
        if source_path.exists():
            shutil.copytree(source_path, self._sandbox_path, dirs_exist_ok=True)
        return self._sandbox_path

    async def cleanup(self) -> None:
        if self._sandbox_path and self._sandbox_path.exists():
            shutil.rmtree(self._sandbox_path)
            self._sandbox_path = None

    async def run_command(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: int = 300,
    ) -> CommandResult:
        return CommandResult(returncode=0, stdout="OK", stderr="", duration_ms=10)

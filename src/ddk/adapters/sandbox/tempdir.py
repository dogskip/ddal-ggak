"""Temporary-directory sandbox implementation."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .base import CommandResult


class TempDirSandbox:
    """Copy the target repository into a disposable temporary directory."""

    def __init__(self) -> None:
        self._sandbox_path: Path | None = None

    async def create(self, source_path: Path) -> Path:
        """Create a temporary sandbox and copy source files into it."""
        self._sandbox_path = Path(tempfile.mkdtemp(prefix="ddk-sandbox-"))
        if source_path.exists():
            shutil.copytree(source_path, self._sandbox_path, dirs_exist_ok=True)
        return self._sandbox_path

    async def cleanup(self) -> None:
        """Remove the temporary sandbox directory if it exists."""
        if self._sandbox_path is not None and self._sandbox_path.exists():
            shutil.rmtree(self._sandbox_path)
            self._sandbox_path = None

    async def run_command(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: int = 300,
    ) -> CommandResult:
        """This sandbox delegates command execution to the build runner."""
        return CommandResult(returncode=0, stdout="", stderr="", duration_ms=0)

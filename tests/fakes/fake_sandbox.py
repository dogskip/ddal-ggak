"""TempDirSandbox — uses tempfile.mkdtemp() instead of git worktree."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ddk.adapters.sandbox.base import CommandResult


class TempDirSandbox:
    """Lightweight test double — creates an empty temp dir without copying files."""

    def __init__(self) -> None:
        self._sandbox_path: Path | None = None

    async def create(self, source_path: Path) -> Path:
        self._sandbox_path = Path(tempfile.mkdtemp(prefix="ddk-sandbox-"))
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


class ProjectSandbox(TempDirSandbox):
    """TempDirSandbox whose directory starts out holding the given project files."""

    def __init__(self, files: dict[str, str] | None = None) -> None:
        super().__init__()
        self._files = files or {}

    async def create(self, source_path: Path) -> Path:
        root = await super().create(source_path)
        for name, content in self._files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return root

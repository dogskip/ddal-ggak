"""Sandbox adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class CommandResult:
    """Result of running a command in the sandbox."""

    returncode: int
    stdout: str
    stderr: str
    duration_ms: int = 0


@runtime_checkable
class SandboxAdapter(Protocol):
    """Protocol for sandbox execution environments."""

    async def create(self, source_path: Path) -> Path: ...

    async def cleanup(self) -> None: ...

    async def run_command(
        self,
        command: list[str],
        cwd: Path | None = None,
        timeout: int = 300,
    ) -> CommandResult: ...

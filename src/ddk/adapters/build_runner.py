"""Build runner adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class BuildResult:
    """Result of a build command execution."""

    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration_ms: int = 0


@runtime_checkable
class BuildRunner(Protocol):
    """Protocol for running build commands (npm build, tsc, etc.)."""

    async def run(self, command: list[str], cwd: Path, timeout: int = 300) -> BuildResult: ...

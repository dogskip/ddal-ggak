"""Temporary-directory sandbox implementation."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path

from ddk.security.secret_paths import is_secret_path

from .base import CommandResult
from .policy import ALLOWED_COMMANDS, is_command_allowed, is_env_allowed

# Never copied, at any depth.
_EXCLUDED_ANYWHERE = frozenset({".git", ".ddk", ".ddk-home", "__pycache__"})
# Build output and caches; dropped only at the repository root.
_EXCLUDED_AT_ROOT = frozenset({"dist", ".next", ".turbo", "coverage", ".venv"})


class TempDirSandbox:
    """Copy the target repository into a disposable temporary directory."""

    def __init__(self) -> None:
        self._sandbox_path: Path | None = None

    async def create(self, source_path: Path) -> Path:
        """Create a temporary sandbox and copy source files into it."""
        self._sandbox_path = Path(tempfile.mkdtemp(prefix="ddk-sandbox-"))
        if source_path.exists():
            source_root = source_path.resolve()

            def ignore_unsafe_symlinks(directory: str, names: list[str]) -> list[str]:
                ignored: list[str] = []
                relative_dir = Path(directory).relative_to(source_path)
                for name in names:
                    candidate = Path(directory) / name
                    relative = (relative_dir / name).as_posix()
                    if (
                        name in _EXCLUDED_ANYWHERE
                        or (relative_dir == Path() and name in _EXCLUDED_AT_ROOT)
                        or is_secret_path(relative)
                    ):
                        ignored.append(name)
                        continue
                    if not candidate.is_symlink():
                        continue
                    try:
                        target = candidate.readlink()
                        resolved_target = candidate.resolve(strict=False)
                    except OSError:
                        ignored.append(name)
                        continue
                    if target.is_absolute() or not resolved_target.is_relative_to(source_root):
                        ignored.append(name)
                return ignored

            shutil.copytree(
                source_path,
                self._sandbox_path,
                dirs_exist_ok=True,
                symlinks=True,
                ignore=ignore_unsafe_symlinks,
            )
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
        """Execute a command inside the sandbox with policy enforcement.

        The command's base executable must be in the ALLOWED_COMMANDS set.
        Environment variables are filtered through the ENV_WHITELIST.
        """
        if not command:
            return CommandResult(returncode=1, stdout="", stderr="Empty command", duration_ms=0)

        if not is_command_allowed(command[0]):
            return CommandResult(
                returncode=126,
                stdout="",
                stderr=f"Command not allowed: {command[0]}. Allowed: {sorted(ALLOWED_COMMANDS)}",
                duration_ms=0,
            )

        work_dir = cwd or self._sandbox_path
        env = {k: v for k, v in os.environ.items() if is_env_allowed(k)}

        start = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(work_dir) if work_dir else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                returncode=process.returncode or 0,
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                duration_ms=duration_ms,
            )
        except TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            return CommandResult(
                returncode=124,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=duration_ms,
            )

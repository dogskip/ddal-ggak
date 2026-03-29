"""Temporary-directory sandbox implementation."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from pathlib import Path

from .base import CommandResult
from .policy import ALLOWED_COMMANDS, is_command_allowed, is_env_allowed


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

"""Subprocess-based BuildRunner implementation."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from pathlib import Path

from .build_runner import BuildResult
from .sandbox.policy import is_command_allowed, is_env_allowed


class SubprocessBuildRunner:
    """Run build commands in a subprocess with timeout handling."""

    async def run(
        self,
        command: list[str],
        cwd: Path,
        timeout: int = 300,
    ) -> BuildResult:
        """Execute a command and capture stdout, stderr, and duration."""
        start = time.monotonic()
        if not command or not is_command_allowed(command[0]):
            executable = command[0] if command else ""
            return BuildResult(
                success=False,
                stdout="",
                stderr=f"Command not allowed: {executable}",
                returncode=126,
                duration_ms=0,
            )

        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=str(cwd),
                env=child_environment(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError:
            return BuildResult(
                success=False,
                stdout="",
                stderr=f"Command not found: {command[0]}",
                returncode=127,
                duration_ms=0,
            )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            kill_process_tree(process)
            await process.communicate()
            return BuildResult(
                success=False,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                returncode=124,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return BuildResult(
            success=process.returncode == 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            returncode=process.returncode or 0,
            duration_ms=duration_ms,
        )


def child_environment(cwd: Path) -> dict[str, str]:
    """Allow-listed environment for child tools, with HOME and the npm cache inside ``cwd``."""
    sandbox_home = cwd / ".ddk-home"
    sandbox_home.mkdir(parents=True, exist_ok=True)
    env = {
        key: value
        for key, value in os.environ.items()
        if is_env_allowed(key) and key not in {"HOME", "npm_config_cache"}
    }
    env["HOME"] = str(sandbox_home)
    env["npm_config_cache"] = str(sandbox_home / ".npm-cache")
    env["NO_COLOR"] = "1"
    return env


def kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """Kill the child and everything it spawned (npm → node → vite ...)."""
    if hasattr(os, "killpg"):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(process.pid, signal.SIGKILL)
            return
    process.kill()

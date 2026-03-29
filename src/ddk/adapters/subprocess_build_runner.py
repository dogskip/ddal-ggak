"""Subprocess-based BuildRunner implementation."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from .build_runner import BuildResult


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
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
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
            stdout=stdout.decode(),
            stderr=stderr.decode(),
            returncode=process.returncode or 0,
            duration_ms=duration_ms,
        )

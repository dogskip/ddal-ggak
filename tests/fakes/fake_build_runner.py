"""FakeBuildRunner — configurable returncode and stderr for unit tests."""

from __future__ import annotations

from pathlib import Path

from ddk.adapters.sandbox.base import CommandResult


class FakeBuildRunner:
    """Returns configurable CommandResult. Records all run() calls."""

    def __init__(
        self,
        returncode: int = 0,
        stdout: str = "Build OK",
        stderr: str = "",
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.run_log: list[dict[str, object]] = []

    async def run(
        self,
        command: list[str],
        cwd: Path,
        timeout: int = 300,
    ) -> CommandResult:
        self.run_log.append({"command": command, "cwd": str(cwd), "timeout": timeout})
        return CommandResult(
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
            duration_ms=10,
        )

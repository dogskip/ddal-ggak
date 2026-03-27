"""FakeSubprocessRunner — returns pre-configured BuildResult."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ddk.adapters.build_runner import BuildResult


class FakeSubprocessRunner:
    """Returns pre-configured BuildResult. Records all commands run."""

    def __init__(
        self,
        results: dict[str, BuildResult] | None = None,
        default_success: bool = True,
    ):
        self.results: dict[str, BuildResult] = results or {}
        self.default_success = default_success
        self.run_log: list[dict[str, Any]] = []

    async def run(
        self, command: list[str], cwd: Path, timeout: int = 300
    ) -> BuildResult:
        key = " ".join(command)
        self.run_log.append(
            {"command": command, "cwd": str(cwd), "timeout": timeout}
        )
        if key in self.results:
            return self.results[key]
        return BuildResult(
            success=self.default_success,
            stdout="OK" if self.default_success else "",
            stderr="" if self.default_success else "Error",
            returncode=0 if self.default_success else 1,
            duration_ms=10,
        )

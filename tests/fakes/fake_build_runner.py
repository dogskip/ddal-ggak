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


class ScriptedBuildRunner:
    """Answers each command from a table keyed by the joined command line.

    Unlisted commands succeed with empty output. Every call is recorded in ``run_log``.
    The placeholder ``/work/app`` in captured output is replaced by the real ``cwd``,
    so recorded tool output can be replayed against any sandbox directory.
    """

    PLACEHOLDER_ROOT = "/work/app"

    def __init__(self, results: dict[str, CommandResult] | None = None) -> None:
        self.results = results or {}
        self.run_log: list[dict[str, object]] = []

    async def run(
        self,
        command: list[str],
        cwd: Path,
        timeout: int = 300,
    ) -> CommandResult:
        self.run_log.append({"command": command, "cwd": str(cwd), "timeout": timeout})
        canned = self.results.get(
            " ".join(command),
            CommandResult(returncode=0, stdout="", stderr="", duration_ms=1),
        )
        return CommandResult(
            returncode=canned.returncode,
            stdout=canned.stdout.replace(self.PLACEHOLDER_ROOT, str(cwd)),
            stderr=canned.stderr.replace(self.PLACEHOLDER_ROOT, str(cwd)),
            duration_ms=canned.duration_ms,
        )

    def commands(self) -> list[str]:
        return [" ".join(str(part) for part in entry["command"]) for entry in self.run_log]  # type: ignore[attr-defined]

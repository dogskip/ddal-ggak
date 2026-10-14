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

MAX_OUTPUT_BYTES = 10 * 1024 * 1024
CLEANUP_TIMEOUT_S = 10.0
_READ_BYTES = 64 * 1024


class ProcessCleanupError(RuntimeError):
    """An owned process group or its output did not finish within the cleanup budget."""


class ProcessOutput:
    """Concurrent, bounded stdout and stderr for one directly created process group."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self.process = process
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.exceeded = asyncio.Event()
        self._size = 0
        self._terminated = False
        self._readers: list[asyncio.Task[None]] = []
        self.done = asyncio.create_task(self._collect())

    async def _collect(self) -> None:
        assert self.process.stdout is not None and self.process.stderr is not None
        self._readers = [
            asyncio.create_task(self._drain(self.process.stdout, self.stdout)),
            asyncio.create_task(self._drain(self.process.stderr, self.stderr)),
        ]
        await asyncio.gather(*self._readers)
        await self.process.wait()

    async def _drain(self, stream: asyncio.StreamReader, target: bytearray) -> None:
        while chunk := await stream.read(_READ_BYTES):
            available = MAX_OUTPUT_BYTES - self._size
            kept = chunk[:available]
            target.extend(kept)
            self._size += len(kept)
            if len(chunk) > available and not self.exceeded.is_set():
                self.exceeded.set()
                self.terminate()

    def terminate(self) -> None:
        if not self._terminated:
            kill_process_tree(self.process)
            self._terminated = True

    def text(self, reason: str = "") -> tuple[str, str]:
        suffix = ("\n" + reason).encode() if reason else b""
        budget = MAX_OUTPUT_BYTES - len(suffix)
        stdout = bytes(self.stdout).decode(errors="replace").encode()[:budget]
        stdout_text = stdout.decode(errors="ignore")
        budget -= len(stdout_text.encode())
        stderr = bytes(self.stderr).decode(errors="replace").encode()[:budget]
        return stdout_text, stderr.decode(errors="ignore") + suffix.decode()

    async def wait(self, deadline_ns: int) -> bool:
        exceeded = asyncio.create_task(self.exceeded.wait())
        try:
            done, _ = await asyncio.wait(
                {self.done, exceeded},
                timeout=max(0, (deadline_ns - time.monotonic_ns()) / 1e9),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if self.exceeded.is_set():
                return True
            if self.done not in done:
                raise TimeoutError
            self.done.result()
            return False
        finally:
            exceeded.cancel()
            await asyncio.gather(exceeded, return_exceptions=True)

    def close(self) -> None:
        for reader in self._readers:
            reader.cancel()
        self.done.cancel()
        transport = getattr(self.process, "_transport", None)
        if transport is not None:
            transport.close()


async def stop_owned_process(
    process: asyncio.subprocess.Process,
    output: ProcessOutput,
    *,
    deadline_ns: int | None = None,
) -> None:
    """Terminate the session created by this adapter and bound every output wait."""
    if deadline_ns is None:
        deadline_ns = time.monotonic_ns() + int(CLEANUP_TIMEOUT_S * 1e9)
    cancelled = False
    try:
        output.terminate()
        while not output.done.done():
            remaining = (deadline_ns - time.monotonic_ns()) / 1e9
            if remaining <= 0:
                raise ProcessCleanupError("Process cleanup timed out; output drain incomplete")
            try:
                await asyncio.wait({output.done}, timeout=remaining)
            except asyncio.CancelledError:
                cancelled = True
        output.done.result()
    except BaseException:
        output.close()
        raise
    if cancelled:
        raise asyncio.CancelledError


async def start_owned_process(
    command: list[str], cwd: Path, *, stdin: int | None = None
) -> tuple[asyncio.subprocess.Process, ProcessOutput]:
    """Retain ownership when cancellation races with subprocess creation."""
    abandoned = False
    cleanup_deadline_ns: int | None = None

    async def create() -> tuple[asyncio.subprocess.Process, ProcessOutput]:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(cwd),
            env=child_environment(cwd),
            stdin=stdin,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        output = ProcessOutput(process)
        if abandoned:
            await stop_owned_process(process, output, deadline_ns=cleanup_deadline_ns)
        return process, output

    creation = asyncio.create_task(create())
    try:
        return await asyncio.shield(creation)
    except asyncio.CancelledError as exc:
        abandoned = True
        cleanup_deadline_ns = time.monotonic_ns() + int(CLEANUP_TIMEOUT_S * 1e9)
        try:
            while not creation.done():
                remaining = (cleanup_deadline_ns - time.monotonic_ns()) / 1e9
                if remaining <= 0:
                    creation.add_done_callback(
                        lambda completed: None if completed.cancelled() else completed.exception()
                    )
                    raise ProcessCleanupError("Process creation cleanup timed out")
                try:
                    await asyncio.wait({creation}, timeout=remaining)
                except asyncio.CancelledError:
                    continue
            process, output = creation.result()
            await stop_owned_process(process, output, deadline_ns=cleanup_deadline_ns)
        except Exception as cleanup:
            exc.add_note(f"Process cleanup failed: {cleanup}")
        raise


class SubprocessBuildRunner:
    """Run build commands in a subprocess with timeout handling."""

    async def run(
        self,
        command: list[str],
        cwd: Path,
        timeout: int = 300,
    ) -> BuildResult:
        """Execute a command and capture stdout, stderr, and duration."""
        start_ns = time.monotonic_ns()
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
            process, output = await start_owned_process(command, cwd)
        except FileNotFoundError:
            return BuildResult(
                success=False,
                stdout="",
                stderr=f"Command not found: {command[0]}",
                returncode=127,
                duration_ms=0,
            )
        reason = ""
        forced_code: int | None = None
        try:
            if await output.wait(start_ns + int(timeout * 1e9)):
                reason = "Command output limit exceeded (10 MiB combined stdout/stderr)"
                forced_code = 125
        except TimeoutError:
            reason = f"Command timed out after {timeout}s"
            forced_code = 124
        except BaseException as exc:
            try:
                await stop_owned_process(process, output)
            except Exception as cleanup:
                exc.add_note(f"Process cleanup failed: {cleanup}")
            raise
        try:
            await stop_owned_process(process, output)
        except Exception as exc:
            reason = f"{reason}; Process cleanup failed: {exc}".lstrip("; ")
            forced_code = 125
        stdout, stderr = output.text(reason)
        returncode = forced_code if forced_code is not None else (process.returncode or 0)
        return BuildResult(
            success=returncode == 0,
            stdout=stdout,
            stderr=stderr,
            returncode=returncode,
            duration_ms=(time.monotonic_ns() - start_ns) // 1_000_000,
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
    """Signal only the new session owned by the process returned from subprocess creation."""
    if hasattr(os, "killpg"):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        return
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()

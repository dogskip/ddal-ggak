"""Preview launcher that runs the server as a child process in its own session."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import time
from dataclasses import dataclass, field
from pathlib import Path

from .preview import PreviewStartError
from .sandbox.policy import is_command_allowed
from .subprocess_build_runner import ProcessOutput, start_owned_process, stop_owned_process

_HOST = "127.0.0.1"
_POLL_S = 0.1
_TAIL_CHARS = 600


@dataclass
class _Session:
    url: str
    _process: asyncio.subprocess.Process
    _output: ProcessOutput
    _stopped: bool = field(default=False)

    def output(self) -> tuple[str, str]:
        """Return bounded stdout and stderr collected from this owned process."""
        return self._output.text()

    async def stop(self) -> None:
        if self._stopped:
            return
        try:
            await stop_owned_process(self._process, self._output)
        except Exception as exc:
            raise PreviewStartError(f"Preview cleanup failed: {exc}") from exc
        self._stopped = True
        if self._output.exceeded.is_set():
            raise PreviewStartError("Preview output limit exceeded (10 MiB combined stdout/stderr)")


class SubprocessPreviewLauncher:
    """Runs ``command`` with a sanitized environment until its port accepts connections."""

    async def start(self, command: list[str], cwd: Path, *, timeout_s: float = 60.0) -> _Session:
        if not command or not is_command_allowed(command[0]):
            raise PreviewStartError(f"Command not allowed: {command[0] if command else ''}")
        started_ns = time.monotonic_ns()
        port = _free_port()
        argv = [part.replace("{port}", str(port)) for part in command]
        try:
            process, output = await start_owned_process(argv, cwd, stdin=asyncio.subprocess.DEVNULL)
        except FileNotFoundError as exc:
            raise PreviewStartError(f"Command not found: {argv[0]}") from exc
        session = _Session(url=f"http://{_HOST}:{port}/", _process=process, _output=output)
        try:
            await _wait_until_listening(
                process, port, timeout_s, started_ns + int(timeout_s * 1e9), output
            )
        except BaseException as exc:
            try:
                await session.stop()
            except Exception as cleanup:
                exc.add_note(f"Preview cleanup failed: {cleanup}")
            raise
        return session


async def _wait_until_listening(
    process: asyncio.subprocess.Process,
    port: int,
    timeout_s: float,
    deadline_ns: int,
    output: ProcessOutput,
) -> None:
    while True:
        if output.exceeded.is_set():
            raise PreviewStartError("Preview output limit exceeded (10 MiB combined stdout/stderr)")
        if process.returncode is not None:
            raise PreviewStartError(
                f"preview server exited with code {process.returncode}: {_tail(output)}"
            )
        remaining = (deadline_ns - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise PreviewStartError(
                f"preview server did not start listening within {timeout_s:g}s: {_tail(output)}"
            )
        try:
            if await asyncio.wait_for(_accepts(port), timeout=min(remaining, _POLL_S)):
                return
        except TimeoutError:
            pass
        await asyncio.sleep(min(_POLL_S, max(0, (deadline_ns - time.monotonic_ns()) / 1e9)))


async def _accepts(port: int) -> bool:
    try:
        _, writer = await asyncio.open_connection(_HOST, port)
    except OSError:
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((_HOST, 0))
        return int(sock.getsockname()[1])


def _tail(output: ProcessOutput) -> str:
    stdout, stderr = output.text()
    text = (stdout + stderr).strip()
    return text[-_TAIL_CHARS:] if text else "no output"

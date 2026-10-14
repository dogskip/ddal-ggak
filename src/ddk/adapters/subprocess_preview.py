"""Preview launcher that runs the server as a child process in its own session."""

from __future__ import annotations

import asyncio
import contextlib
import socket
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .preview import PreviewStartError
from .sandbox.policy import is_command_allowed
from .subprocess_build_runner import child_environment, kill_process_tree

_HOST = "127.0.0.1"
_POLL_S = 0.1
_TAIL_CHARS = 600


@dataclass
class _Session:
    url: str
    _process: asyncio.subprocess.Process
    _log: Path
    _stopped: bool = field(default=False)

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._process.returncode is None:
            kill_process_tree(self._process)
            with contextlib.suppress(ProcessLookupError):
                await self._process.wait()
        with contextlib.suppress(OSError):
            self._log.unlink()


class SubprocessPreviewLauncher:
    """Runs ``command`` with a sanitized environment until its port accepts connections."""

    async def start(self, command: list[str], cwd: Path, *, timeout_s: float = 60.0) -> _Session:
        if not command or not is_command_allowed(command[0]):
            raise PreviewStartError(f"Command not allowed: {command[0] if command else ''}")

        port = _free_port()
        argv = [part.replace("{port}", str(port)) for part in command]
        log_file = tempfile.NamedTemporaryFile(  # noqa: SIM115
            prefix="ddk-preview-", suffix=".log", delete=False
        )
        log_path = Path(log_file.name)
        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=child_environment(cwd),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=log_file,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            log_path.unlink(missing_ok=True)
            raise PreviewStartError(f"Command not found: {argv[0]}") from exc
        finally:
            log_file.close()

        session = _Session(url=f"http://{_HOST}:{port}/", _process=process, _log=log_path)
        try:
            await _wait_until_listening(process, port, timeout_s, log_path)
        except BaseException:
            await session.stop()
            raise
        return session


async def _wait_until_listening(
    process: asyncio.subprocess.Process, port: int, timeout_s: float, log_path: Path
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while True:
        if process.returncode is not None:
            raise PreviewStartError(
                f"preview server exited with code {process.returncode}: {_tail(log_path)}"
            )
        if await _accepts(port):
            return
        if loop.time() >= deadline:
            raise PreviewStartError(
                f"preview server did not start listening within {timeout_s:g}s: {_tail(log_path)}"
            )
        await asyncio.sleep(_POLL_S)


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


def _tail(log_path: Path) -> str:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "no output"
    return text[-_TAIL_CHARS:] if text else "no output"

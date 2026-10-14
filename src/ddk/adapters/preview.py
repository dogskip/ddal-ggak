"""Preview launcher Protocol: serve a built web app on loopback for browser checks."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


class PreviewStartError(RuntimeError):
    """The preview server could not be started or never began listening."""


@runtime_checkable
class PreviewSession(Protocol):
    """A running preview server."""

    url: str

    async def stop(self) -> None: ...


@runtime_checkable
class PreviewLauncher(Protocol):
    """Starts a preview server. ``{port}`` in ``command`` is replaced with a free port."""

    async def start(
        self, command: list[str], cwd: Path, *, timeout_s: float = 60.0
    ) -> PreviewSession: ...

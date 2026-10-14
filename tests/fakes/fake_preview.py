"""FakePreviewLauncher — pretends to serve the sandbox and records how it was used."""

from __future__ import annotations

from pathlib import Path

from ddk.adapters.preview import PreviewStartError


class FakePreviewSession:
    def __init__(self, url: str, launcher: FakePreviewLauncher, cwd: Path) -> None:
        self.url = url
        self._launcher = launcher
        self._cwd = cwd

    async def stop(self) -> None:
        self._launcher.stopped += 1
        self._launcher.cwd_existed_at_stop = self._cwd.exists()


class FakePreviewLauncher:
    """Serves nothing; ``fail_with`` makes ``start`` raise PreviewStartError."""

    def __init__(
        self, *, fail_with: str | None = None, url: str = "http://127.0.0.1:4173/"
    ) -> None:
        self._fail_with = fail_with
        self._url = url
        self.started: list[tuple[list[str], Path]] = []
        self.cwd_existed_at_start: bool | None = None
        self.cwd_existed_at_stop: bool | None = None
        self.stopped = 0

    async def start(
        self, command: list[str], cwd: Path, *, timeout_s: float = 60.0
    ) -> FakePreviewSession:
        self.started.append((command, cwd))
        self.cwd_existed_at_start = cwd.exists()
        if self._fail_with is not None:
            raise PreviewStartError(self._fail_with)
        return FakePreviewSession(self._url, self, cwd)

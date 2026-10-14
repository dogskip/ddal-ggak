"""FakePlaywrightAdapter — returns configurable screenshot path and console entries."""

from __future__ import annotations

from pathlib import Path

from ddk.adapters.playwright_browser import ConsoleEntry, FailedRequestEntry


class FakePlaywrightAdapter:
    """Returns configurable SSIM score and fixture screenshot path."""

    def __init__(
        self,
        screenshot_path: Path | None = None,
        console_errors: list[ConsoleEntry] | None = None,
        failed_requests: list[FailedRequestEntry] | None = None,
    ):
        self.screenshot_path = screenshot_path or Path("/tmp/fake-screenshot.png")
        self.console_errors = console_errors or []
        self.failed_requests: list[FailedRequestEntry] = failed_requests or []
        self.capture_log: list[dict[str, object]] = []
        self._closed = False

    async def capture_screenshot(
        self,
        url: str,
        output_path: Path,
        viewport: tuple[int, int] = (1280, 800),
    ) -> Path:
        self.capture_log.append({"url": url, "output_path": str(output_path), "viewport": viewport})
        return self.screenshot_path

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]:
        return self.console_errors

    async def get_failed_requests(
        self,
        url: str,
        wait_ms: int = 5000,
        correlation_id: str | None = None,
    ) -> list[FailedRequestEntry]:
        return self.failed_requests

    async def close(self) -> None:
        self._closed = True


class PaintingBrowser:
    """A browser whose "page" is a PNG of one colour, optionally with a differing box."""

    is_null = False

    def __init__(
        self,
        *,
        color: tuple[int, int, int] = (255, 255, 255),
        box: tuple[tuple[int, int, int, int], tuple[int, int, int]] | None = None,
        size: tuple[int, int] = (320, 200),
        console_errors: list[ConsoleEntry] | None = None,
        failed_requests: list[FailedRequestEntry] | None = None,
        unavailable: str | None = None,
    ) -> None:
        self.color = color
        self.box = box
        self.size = size
        self.console_errors = console_errors or []
        self.failed_requests = failed_requests or []
        self.unavailable = unavailable
        self.visited: list[str] = []
        self.viewports: list[tuple[int, int]] = []

    def _check(self) -> None:
        if self.unavailable is not None:
            from ddk.adapters.chromium_browser import BrowserUnavailableError

            raise BrowserUnavailableError(self.unavailable)

    async def capture_screenshot(
        self,
        url: str,
        output_path: Path,
        viewport: tuple[int, int] = (1280, 800),
    ) -> Path:
        from PIL import Image, ImageDraw

        self._check()
        self.visited.append(url)
        self.viewports.append(viewport)
        image = Image.new("RGB", self.size, self.color)
        if self.box is not None:
            ImageDraw.Draw(image).rectangle(self.box[0], fill=self.box[1])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)
        return output_path

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]:
        self._check()
        return self.console_errors

    async def get_failed_requests(
        self,
        url: str,
        wait_ms: int = 5000,
        correlation_id: str | None = None,
    ) -> list[FailedRequestEntry]:
        self._check()
        return self.failed_requests

    async def close(self) -> None:
        return None

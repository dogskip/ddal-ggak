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

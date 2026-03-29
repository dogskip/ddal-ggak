"""Minimal Playwright adapter for non-visual CLI runs."""

from __future__ import annotations

from pathlib import Path

from .playwright_browser import ConsoleEntry, FailedRequestEntry


class NullPlaywrightAdapter:
    """Return empty browser diagnostics when no live browser is configured."""

    async def capture_screenshot(
        self,
        url: str,
        output_path: Path,
        viewport: tuple[int, int] = (1280, 800),
    ) -> Path:
        """Return the requested output path without performing browser work."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    async def get_console_errors(
        self,
        url: str,
        wait_ms: int = 5000,
    ) -> list[ConsoleEntry]:
        """Return no console errors."""
        return []

    async def get_failed_requests(
        self,
        url: str,
        wait_ms: int = 5000,
        correlation_id: str | None = None,
    ) -> list[FailedRequestEntry]:
        """Return no failed network requests."""
        return []

    async def close(self) -> None:
        """Close the no-op browser adapter."""
        return None

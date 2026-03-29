"""Playwright browser adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class ConsoleEntry:
    """A single browser console log entry."""

    level: str  # "log", "warn", "error"
    message: str
    url: str | None = None
    line_number: int | None = None


@dataclass
class FailedRequestEntry:
    """A single failed network request captured by Playwright."""

    url: str
    failure_text: str  # playwright request.failure property (str | None → str)
    correlation_id: str | None = None


@runtime_checkable
class PlaywrightAdapter(Protocol):
    """Protocol for browser automation via Playwright."""

    async def capture_screenshot(
        self,
        url: str,
        output_path: Path,
        viewport: tuple[int, int] = (1280, 800),
    ) -> Path: ...

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]: ...

    async def get_failed_requests(
        self,
        url: str,
        wait_ms: int = 5000,
        correlation_id: str | None = None,
    ) -> list[FailedRequestEntry]: ...

    async def close(self) -> None: ...

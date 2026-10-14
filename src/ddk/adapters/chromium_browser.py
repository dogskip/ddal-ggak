"""Headless Chromium through Playwright: screenshots, console errors, failed requests.

Generated code runs in this browser, so it may only talk to loopback addresses; every other
request is aborted and listed in ``blocked_requests``. Playwright is imported on first use.
Without a Playwright-installed Chromium, a Chrome or Edge that is already installed is used.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from .playwright_browser import ConsoleEntry, FailedRequestEntry
from .system_browser import find_system_browser

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright, Request, Response, Route

_LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_INLINE_SCHEMES = frozenset({"data", "blob", "about"})
_SETTLE_MS = 300
_IGNORED_PATHS = frozenset({"/favicon.ico"})
_RESOURCE_NOISE = "Failed to load resource"
_CANCELLED = "net::ERR_ABORTED"
_MISSING_BINARY = "Executable doesn't exist"
PLAYWRIGHT_BUILD = "Playwright's Chromium"


class BrowserUnavailableError(RuntimeError):
    """Playwright or its Chromium build cannot be used on this machine."""


def is_local_url(url: str) -> bool:
    """Whether the URL stays on this machine (loopback host or inline data)."""
    parsed = urlparse(url)
    if parsed.scheme in _INLINE_SCHEMES:
        return True
    return (parsed.hostname or "") in _LOCAL_HOSTS


def _playwright_factory() -> Callable[[], Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise BrowserUnavailableError(
            "Playwright is not installed; reinstall ddalggak so its dependencies are complete"
        ) from exc
    return async_playwright


@dataclass
class _PageEvents:
    console: list[ConsoleEntry] = field(default_factory=lambda: list[ConsoleEntry]())
    failed: list[tuple[str, str]] = field(default_factory=lambda: list[tuple[str, str]]())


class ChromiumBrowserAdapter:
    """Playwright adapter that opens a fresh isolated page per call."""

    is_null: bool = False

    def __init__(
        self,
        *,
        executable_path: Path | str | None = None,
        timeout_ms: int = 30_000,
    ) -> None:
        self._executable_path = str(executable_path) if executable_path else None
        self._timeout_ms = timeout_ms
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._started = PLAYWRIGHT_BUILD
        self.blocked_requests: list[str] = []

    async def capture_screenshot(
        self,
        url: str,
        output_path: Path,
        viewport: tuple[int, int] = (1280, 800),
    ) -> Path:
        """Full-page PNG of ``url`` rendered at the given viewport."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with self._visit(url, viewport, wait_ms=5000) as (page, _):
            await page.screenshot(
                path=str(output_path), full_page=True, animations="disabled", caret="hide"
            )
        return output_path

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]:
        """Console errors and uncaught exceptions seen while loading ``url``."""
        async with self._visit(url, (1280, 800), wait_ms) as (_, events):
            pass
        return events.console

    async def get_failed_requests(
        self,
        url: str,
        wait_ms: int = 5000,
        correlation_id: str | None = None,
    ) -> list[FailedRequestEntry]:
        """Requests that failed or answered with an HTTP error while loading ``url``."""
        async with self._visit(url, (1280, 800), wait_ms) as (_, events):
            pass
        return [
            FailedRequestEntry(url=request_url, failure_text=text, correlation_id=correlation_id)
            for request_url, text in events.failed
        ]

    async def probe(self) -> str:
        """Start and stop the browser a run would use; returns which one it is."""
        try:
            await self._ensure_browser()
            return self._started
        finally:
            await self.close()

    async def close(self) -> None:
        """Shut the browser down; safe to call repeatedly."""
        browser, playwright = self._browser, self._playwright
        self._browser = self._playwright = None
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

    # ------------------------------------------------------------------

    @asynccontextmanager
    async def _visit(
        self, url: str, viewport: tuple[int, int], wait_ms: int
    ) -> AsyncGenerator[tuple[Page, _PageEvents]]:
        browser = await self._ensure_browser()
        context = await browser.new_context(
            viewport={"width": viewport[0], "height": viewport[1]},
            accept_downloads=False,
            service_workers="block",
            reduced_motion="reduce",
        )
        try:
            page = await context.new_page()
            events = _PageEvents()
            await context.route("**/*", self._gate)
            page.on("console", lambda message: self._on_console(events, message))
            page.on("pageerror", lambda error: events.console.append(_uncaught(error)))
            page.on("requestfailed", lambda request: self._on_request_failed(events, request))
            page.on("response", lambda response: _on_response(events, response))

            await page.goto(url, wait_until="load", timeout=self._timeout_ms)
            with contextlib.suppress(Exception):
                await page.wait_for_load_state("networkidle", timeout=wait_ms)
            await page.wait_for_timeout(_SETTLE_MS)
            yield page, events
        finally:
            await context.close()

    async def _ensure_browser(self) -> Browser:
        if self._browser is not None:
            return self._browser
        factory = _playwright_factory()
        self._playwright = await factory().start()
        try:
            return await self._launch(self._executable_path)
        except Exception as first:  # noqa: BLE001 - Playwright raises plain exceptions
            failure = first
        if self._executable_path is None and _MISSING_BINARY in str(failure):
            installed = find_system_browser()
            if installed is not None:
                try:
                    return await self._launch(str(installed))
                except Exception as second:  # noqa: BLE001
                    failure = second
        await self.close()
        raise self._unavailable(failure) from failure

    async def _launch(self, executable_path: str | None) -> Browser:
        assert self._playwright is not None
        args = ["--disable-dev-shm-usage"]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            args.append("--no-sandbox")
        self._browser = await self._playwright.chromium.launch(
            headless=True, executable_path=executable_path, args=args
        )
        self._started = executable_path or PLAYWRIGHT_BUILD
        return self._browser

    def _unavailable(self, failure: Exception) -> BrowserUnavailableError:
        if _MISSING_BINARY not in str(failure):
            return BrowserUnavailableError(f"Chromium could not start: {failure}")
        if self._executable_path is not None:
            return BrowserUnavailableError(
                f"No Chromium at {self._executable_path} (DDK_CHROMIUM_PATH); "
                "fix the path, or unset it to use Playwright's own build"
            )
        return BrowserUnavailableError(
            "No Chromium found; run: ddk doctor --install-browser, install Google Chrome, "
            "or set DDK_CHROMIUM_PATH to an existing Chromium"
        )

    async def _gate(self, route: Route) -> None:
        url = route.request.url
        if is_local_url(url):
            await route.continue_()
            return
        self.blocked_requests.append(url)
        await route.abort("blockedbyclient")

    def _on_console(self, events: _PageEvents, message: Any) -> None:
        if message.type != "error" or str(message.text).startswith(_RESOURCE_NOISE):
            return
        location: dict[str, Any] = message.location or {}
        events.console.append(
            ConsoleEntry(
                level="error",
                message=str(message.text),
                url=location.get("url"),
                line_number=location.get("lineNumber"),
            )
        )

    def _on_request_failed(self, events: _PageEvents, request: Request) -> None:
        reason = request.failure or "request failed"
        if request.url in self.blocked_requests or _ignored(request.url) or reason == _CANCELLED:
            return
        events.failed.append((request.url, reason))


def _on_response(events: _PageEvents, response: Response) -> None:
    if response.status >= 400 and not _ignored(response.url):
        events.failed.append((response.url, f"HTTP {response.status}"))


def _uncaught(error: Any) -> ConsoleEntry:
    return ConsoleEntry(level="error", message=str(getattr(error, "message", error)))


def _ignored(url: str) -> bool:
    return urlparse(url).path in _IGNORED_PATHS

"""ChromiumBrowserAdapter against a real headless Chromium and a local page.

Needs Playwright and a Chromium build (`playwright install chromium`, or DDK_CHROMIUM_PATH).
Skipped when the browser cannot start. Deselect with: pytest -m "not playwright"
"""

from __future__ import annotations

import http.server
import os
import threading
from collections.abc import Iterator
from functools import partial
from pathlib import Path

import pytest
from PIL import Image

from ddk.adapters.chromium_browser import BrowserUnavailableError, ChromiumBrowserAdapter

pytestmark = pytest.mark.playwright

_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>t</title>
<link rel="icon" href="data:,">
</head>
<body style="margin:0;background:#fff">
<div style="width:200px;height:100px;background:#f00"></div>
<script src="/missing.js"></script>
<img src="http://203.0.113.9/tracking.png" alt="">
<script>console.error("page-said-boom");</script>
<script>setTimeout(() => { throw new Error("late-uncaught"); }, 50);</script>
</body></html>
"""


@pytest.fixture
def site(tmp_path: Path) -> Iterator[str]:
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text(_PAGE, encoding="utf-8")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return None

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
async def browser() -> Iterator[ChromiumBrowserAdapter]:
    pytest.importorskip("playwright.async_api")
    adapter = ChromiumBrowserAdapter(executable_path=os.environ.get("DDK_CHROMIUM_PATH"))
    try:
        yield adapter
    finally:
        await adapter.close()


async def test_screenshot_has_the_requested_viewport_and_real_pixels(
    browser: ChromiumBrowserAdapter, site: str, tmp_path: Path
) -> None:
    out = tmp_path / "shots" / "page.png"
    try:
        await browser.capture_screenshot(site, out, viewport=(640, 360))
    except BrowserUnavailableError as exc:
        pytest.skip(str(exc))

    with Image.open(out) as image:
        assert image.width == 640
        pixel = image.convert("RGB").getpixel((10, 10))
    assert pixel == (255, 0, 0)


async def test_console_errors_include_page_errors_but_not_resource_noise(
    browser: ChromiumBrowserAdapter, site: str
) -> None:
    try:
        entries = await browser.get_console_errors(site, wait_ms=1500)
    except BrowserUnavailableError as exc:
        pytest.skip(str(exc))

    messages = [e.message for e in entries]
    assert "page-said-boom" in messages
    assert any("late-uncaught" in m for m in messages)
    assert not any(m.startswith("Failed to load resource") for m in messages)


async def test_failed_requests_report_http_errors_and_skip_blocked_external_hosts(
    browser: ChromiumBrowserAdapter, site: str
) -> None:
    try:
        failed = await browser.get_failed_requests(site, wait_ms=1500, correlation_id="C-001")
    except BrowserUnavailableError as exc:
        pytest.skip(str(exc))

    assert [f.url for f in failed] == [f"{site}missing.js"]
    assert failed[0].failure_text == "HTTP 404"
    assert failed[0].correlation_id == "C-001"
    assert "http://203.0.113.9/tracking.png" in browser.blocked_requests

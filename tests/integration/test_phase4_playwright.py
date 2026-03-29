"""Phase 4 integration tests — real Playwright + local visual diff adapter.

These tests require:
  - Playwright browser binaries: `uv run playwright install chromium`
  - Pillow installed

Skip in CI: pytest -m "not playwright"
"""

from __future__ import annotations

import http.server
import socket
import tempfile
import threading
from functools import partial
from pathlib import Path

import pytest
from PIL import Image

from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter

pytestmark = pytest.mark.playwright


def _reserve_local_port() -> int:
    """Return an available localhost TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _start_html_server(
    html: str,
) -> tuple[http.server.HTTPServer, str, tempfile.TemporaryDirectory[str]]:
    """Serve a single HTML string from a temporary directory."""
    tmpdir = tempfile.TemporaryDirectory(prefix="ddk-playwright-")
    root = Path(tmpdir.name)
    (root / "index.html").write_text(html, encoding="utf-8")

    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            pass

    port = _reserve_local_port()
    handler = partial(SilentHandler, directory=str(root))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{port}", tmpdir


@pytest.mark.asyncio
async def test_playwright_captures_console_errors_from_dev_server() -> None:
    """Real Playwright should capture console errors from a live page."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>ddk integration</title>
</head>
<body>
  <script>
    console.error("test-error-from-ddk-playwright-integration");
  </script>
</body>
</html>
"""
    server, url, tmpdir = _start_html_server(html)
    try:
        pytest.importorskip("playwright.async_api")
        from playwright.async_api import ConsoleMessage, Error, async_playwright

        captured_errors: list[str] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                def on_console(msg: ConsoleMessage) -> None:
                    if msg.type == "error":
                        captured_errors.append(msg.text)

                page.on("console", on_console)
                await page.goto(url, wait_until="domcontentloaded")
                await page.wait_for_timeout(500)
                await browser.close()
        except Error as exc:
            message = str(exc)
            if "Executable doesn't exist" in message or "playwright install" in message:
                pytest.skip(f"Chromium browser binary unavailable: {message}")
            raise

        assert captured_errors, "Expected at least one console error from the page"
        assert any(
            "test-error-from-ddk-playwright-integration" in error for error in captured_errors
        ), f"Expected test error string in captured console output: {captured_errors}"
    finally:
        server.shutdown()
        server.server_close()
        tmpdir.cleanup()


def test_visual_regression_adapter_detects_changes(tmp_path: Path) -> None:
    """Real Pillow-backed adapter should distinguish identical vs changed images."""
    adapter = LocalScreenshotDiffAdapter()
    reference_path = tmp_path / "reference.png"
    identical_path = tmp_path / "identical.png"
    different_path = tmp_path / "different.png"
    diff_path = tmp_path / "diff.png"

    Image.new("RGB", (100, 100), color=(0, 0, 255)).save(reference_path)
    Image.new("RGB", (100, 100), color=(0, 0, 255)).save(identical_path)

    different = Image.new("RGB", (100, 100), color=(0, 0, 255))
    for y in range(50, 100):
        for x in range(100):
            different.putpixel((x, y), (255, 0, 0))
    different.save(different_path)

    identical_result = adapter.compute_ssim(reference_path, identical_path)
    assert identical_result.score > 0.99, (
        f"Identical images should have similarity ≈ 1.0, got {identical_result.score:.4f}"
    )

    different_result = adapter.compute_ssim(reference_path, different_path)
    threshold = 0.92
    assert different_result.score < threshold, (
        f"Different images should have similarity < {threshold}, got {different_result.score:.4f}"
    )
    assert adapter.generate_diff_image(reference_path, different_path, diff_path) == diff_path
    assert diff_path.exists()

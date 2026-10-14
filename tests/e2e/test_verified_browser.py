"""Real headless interaction, context isolation, policy denial and fixed RGB criteria."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import hashlib
import http.server
import json
import platform
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from importlib.metadata import version
from pathlib import Path
from typing import Any

import pytest
from playwright.async_api import Browser, BrowserContext, async_playwright

from ddk.adapters.verified_browser import BrowserSettings, VisualReference, run_flow
from ddk.models.verified_change import record_digest
from tests.unit.adapters.test_verified_browser import FIXTURE, criteria, environment, png, step

pytestmark = pytest.mark.playwright


@pytest.fixture(autouse=True)
async def unhandled_async_errors() -> AsyncIterator[list[dict[str, Any]]]:
    loop = asyncio.get_running_loop()
    previous = loop.get_exception_handler()
    errors: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _, error: errors.append(error))
    try:
        yield errors
        gc.collect()
        await asyncio.sleep(0)
        gc.collect()
    finally:
        loop.set_exception_handler(previous)
    assert not errors, errors


def selector(strategy: str, value: str, name: str | None = None) -> dict[str, Any]:
    return {"strategy": strategy, "value": value, "name": name}


@pytest.fixture
async def settings() -> BrowserSettings:
    env = environment()
    env.update(
        os_name=platform.system(),
        os_version=platform.release(),
        architecture=platform.machine(),
        runtime_name="pytest-local",
        runtime_version=version("pytest"),
        python_version=platform.python_version(),
        node_version="not-used",
        package_manager="not-used",
        package_manager_version="not-used",
    )
    env["fixture_sha256"] = FIXTURE
    env["playwright_version"] = version("playwright")
    env["assurance"] = "trusted-local"
    env["locale"] = "en-US"
    env["timezone"] = "UTC"
    async with async_playwright() as playwright:
        binary = playwright.chromium.executable_path
        if not Path(binary).is_file():
            build = next(
                parent for parent in Path(binary).parents if parent.name.startswith("chromium-")
            )
            shell = build.parent / build.name.replace("chromium-", "chromium_headless_shell-")
            binary = str(next(shell.rglob("chrome-headless-shell")))
        env["browser_binary_sha256"] = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
        browser = await playwright.chromium.launch(
            headless=True, chromium_sandbox=True, executable_path=binary
        )
        try:
            env["browser_version"] = browser.version
        finally:
            await browser.close()
    return BrowserSettings(
        environment=env,
        environment_sha256=record_digest(env),
        frozen_time="2026-10-14T00:00:00+00:00",
        executable_path=binary,
    )


@pytest.fixture
def sites() -> Iterator[tuple[str, list[str], list[str]]]:
    app_hits: list[str] = []
    external_hits: list[str] = []

    class External(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            external_hits.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"external must never be fetched")

        def log_message(self, *_: object) -> None:
            return None

    external = http.server.ThreadingHTTPServer(("127.0.0.1", 0), External)
    external_url = f"http://127.0.0.1:{external.server_port}"
    home = """<label>Search<input aria-label='Search'></label>
<button onclick="localStorage.setItem('counter','1');
document.querySelector('output').textContent='1'">Add</button>
<output data-testid='counter'>0</output><a href='/next'>Continue</a>
<span id='fixed-date'></span><script>
document.querySelector('#fixed-date').textContent=new Date().toISOString()</script>"""

    class App(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            app_hits.append(self.path)
            if self.path == "/slow-missing":
                time.sleep(1)
            if self.path == "/drop":
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            if self.path in {"/redirect", "/internal-redirect"}:
                self.send_response(302)
                self.send_header(
                    "Location",
                    "/next"
                    if self.path == "/internal-redirect"
                    else external_url + "/redirect-leak",
                )
                self.end_headers()
                return
            self.send_response(404 if self.path in {"/missing", "/slow-missing"} else 200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            body = home
            if self.path == "/next":
                body = (
                    "<output></output><script>document.querySelector('output').textContent="
                    "localStorage.getItem('counter') || '0'</script>"
                )
            elif self.path == "/network":
                body = (
                    f"<img src='{external_url}/image'><img src='/redirect'>"
                    f"<script>fetch('{external_url}/fetch').catch(()=>{{}});"
                    f"new WebSocket('{external_url.replace('http:', 'ws:')}/socket');"
                    f"window.open('{external_url}/popup');</script><h1>Network</h1>"
                )
            elif self.path == "/popup-only":
                body = "<h1>Popup</h1><script>window.open('about:blank')</script>"
            elif self.path == "/worker":
                body = (
                    "<h1>Worker</h1><script>navigator.serviceWorker.register('/sw.js')"
                    ".catch(()=>{})</script>"
                )
            elif self.path == "/errors":
                body = (
                    "<h1>Errors</h1><script>console.error('known-console');"
                    "throw Error('known-page-error')</script>"
                )
            elif self.path == "/requests":
                body = "<h1>Requests</h1><script>fetch('/drop').catch(()=>{})</script>"
            elif self.path == "/http":
                body = "<h1>HTTP</h1><script>fetch('/missing')</script>"
            elif self.path == "/late-http":
                body = "<h1>Pending</h1><script>fetch('/slow-missing')</script>"
            elif self.path == "/snapshot":
                body = (
                    "<style>html,body{margin:0;width:100%;height:100%;"
                    "background:rgb(255,0,0)}</style>"
                )
            payload = ("<!doctype html><link rel='icon' href='data:,'>" + body).encode()
            with contextlib.suppress(BrokenPipeError):
                self.wfile.write(payload)

        def log_message(self, *_: object) -> None:
            return None

    app = http.server.ThreadingHTTPServer(("127.0.0.1", 0), App)
    for server in [external, app]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{app.server_port}", app_hits, external_hits
    finally:
        for server in [external, app]:
            server.shutdown()
            server.server_close()


def observation(run: Any, folder: Path) -> dict[str, Any]:
    artifact = next(item for item in run.artifacts if item["kind"] == "data")
    return json.loads((folder / artifact["path"]).read_text())


async def test_steps_share_context_but_different_flows_do_not(
    tmp_path: Path, settings: BrowserSettings, sites: tuple[str, list[str], list[str]]
) -> None:
    steps = [
        step(
            "expect-text",
            selector=selector("css", "#fixed-date"),
            value="2026-10-14T00:00:00.000Z",
            step_id="fixed-time",
        ),
        step("expect-visible", selector=selector("test-id", "counter")),
        step("fill", selector=selector("label", "Search"), value="approved"),
        step("press", selector=selector("label", "Search"), value="Tab"),
        step("click", selector=selector("role", "button", "Add"), step_id="add"),
        step("expect-text", selector=selector("css", "output"), value="1", step_id="count-one"),
        step("click", selector=selector("role", "link", "Continue"), step_id="continue"),
        step("expect-url", value="/next"),
        step("expect-text", selector=selector("css", "output"), value="1", step_id="retained"),
        step("expect-count", selector=selector("css", ".absent"), count=0),
    ]
    flow, check = criteria(steps)
    first = await run_flow(
        flow,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path / "first",
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert first.result["status"] == "passed", observation(first, tmp_path / "first")
    assert first.result["executed_count"] == len(steps)
    assert first.cleanup_complete
    fresh, fresh_check = criteria(
        [
            step("goto", value="/next"),
            step("expect-text", selector=selector("css", "output"), value="0"),
        ]
    )
    second = await run_flow(
        fresh,
        check=fresh_check,
        base_url=sites[0],
        output_dir=tmp_path / "second",
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert second.result["status"] == "passed", observation(second, tmp_path / "second")
    for run, folder in [(first, tmp_path / "first"), (second, tmp_path / "second")]:
        for artifact in run.artifacts:
            path = folder / artifact["path"]
            assert path.stat().st_mode & 0o777 == 0o600
            assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
            assert artifact["size_bytes"] == path.stat().st_size
            assert artifact["sensitive"] and not artifact["public_export_allowed"]


@pytest.mark.parametrize("route", ["/network", "/worker", "/errors", "/requests", "/http"])
async def test_runtime_errors_and_denied_connections_never_pass(
    tmp_path: Path, settings: BrowserSettings, sites: tuple[str, list[str], list[str]], route: str
) -> None:
    payload, check = criteria(
        [step("goto", value=route), step("expect-visible", selector=selector("role", "heading"))]
    )
    result = await run_flow(
        payload,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    data = observation(result, tmp_path)
    assert result.result["status"] == "failed", data
    assert result.cleanup_complete
    codes = {item["code"] for item in data["errors"]}
    if route == "/network":
        assert {
            "external_request_blocked",
            "redirect_blocked",
            "websocket_blocked",
            "popup_blocked",
        } <= codes
        assert sites[2] == []
    elif route == "/worker":
        assert "serviceworker_blocked" in codes
        assert "/sw.js" not in sites[1]
    elif route == "/errors":
        assert {"console_error", "page_error"} <= codes
    elif route == "/http":
        assert "http_error" in codes
    else:
        assert "request_failed" in codes


@pytest.mark.parametrize("matches", [False, True])
async def test_rgb_requires_approved_reference_without_generating_a_baseline(
    tmp_path: Path,
    settings: BrowserSettings,
    sites: tuple[str, list[str], list[str]],
    matches: bool,
) -> None:
    reference = png((255, 0, 0) if matches else (0, 130, 0), (320, 200))
    source_hash = hashlib.sha256(reference).hexdigest()
    payload, check = criteria(
        [
            step("goto", value="/snapshot"),
            step(
                "snapshot",
                reference_path="references/fixed.png",
                rgb_tolerance=0,
                max_mismatch_ppm=0,
            ),
        ]
    )
    result = await run_flow(
        payload,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        settings=settings,
        references={
            "references/fixed.png": VisualReference(
                reference, source_hash, 320, 200, (320, 200), settings.environment_sha256
            )
        },
    )
    data = observation(result, tmp_path)
    assert result.result["status"] == ("passed" if matches else "failed"), data
    assert hashlib.sha256(reference).hexdigest() == source_hash
    assert data["visuals"][0]["mismatch_ppm"] == (0 if matches else 1_000_000)
    assert data["visuals"][0]["ssim"] > 0.99
    assert {item["kind"] for item in result.artifacts} == {
        "screenshot",
        "diff",
        "data",
        "ax_snapshot",
    }


async def test_deadline_and_cancellation_close_browser_and_context(
    tmp_path: Path,
    settings: BrowserSettings,
    sites: tuple[str, list[str], list[str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_closed: list[bool] = []
    contexts_closed: list[bool] = []
    close_browser, close_context = Browser.close, BrowserContext.close

    async def checked_browser(browser: Browser) -> None:
        await close_browser(browser)
        browser_closed.append(not browser.is_connected())

    async def checked_context(context: BrowserContext) -> None:
        pages = context.pages
        await close_context(context)
        contexts_closed.append(all(page.is_closed() for page in pages))

    monkeypatch.setattr(Browser, "close", checked_browser)
    monkeypatch.setattr(BrowserContext, "close", checked_context)
    payload, check = criteria(
        [step("expect-visible", selector=selector("css", ".missing"), timeout_ms=200)]
    )
    result = await run_flow(
        payload,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path / "timeout",
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert result.result["status"] == "failed"
    assert result.result["reason_code"] in {"timeout", "expectation_failed"}
    assert result.cleanup_complete
    report = next(item for item in result.artifacts if item["kind"] == "data")
    data = json.loads((tmp_path / "timeout" / report["path"]).read_text())
    assert data["reason_code"] == result.result["reason_code"]
    assert data["cleanup_complete"]
    payload, check = criteria(
        [step("expect-visible", selector=selector("css", ".missing"), timeout_ms=5000)]
    )
    sites[1].clear()
    task = asyncio.create_task(
        run_flow(
            payload,
            check=check,
            base_url=sites[0],
            output_dir=tmp_path / "cancel",
            fixture_sha256=FIXTURE,
            references={},
            settings=settings,
        )
    )
    async with asyncio.timeout(5):
        while not sites[1]:
            await asyncio.sleep(0.01)
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    records = [p for p in (tmp_path / "cancel").glob("*.json") if not p.name.endswith(".ax.json")]
    assert records and json.loads(records[0].read_text())["cleanup_complete"]
    assert json.loads(records[0].read_text())["reason_code"] == "cancelled"
    assert browser_closed == [True, True]
    assert contexts_closed == [True, True]


@pytest.mark.parametrize(
    "route, expected, reason",
    [
        ("/internal-redirect", "unavailable", "redirect_unavailable"),
        ("/redirect", "failed", "redirect_blocked"),
    ],
)
async def test_internal_redirect_is_explicitly_unavailable_and_external_is_blocked(
    tmp_path: Path,
    settings: BrowserSettings,
    sites: tuple[str, list[str], list[str]],
    route: str,
    expected: str,
    reason: str,
) -> None:
    payload, check = criteria([step("goto", value=route)])
    result = await run_flow(
        payload,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert result.result["status"] == expected, observation(result, tmp_path)
    assert result.result["reason_code"] == reason
    assert result.cleanup_complete
    assert sites[2] == []
    assert "/next" not in sites[1]

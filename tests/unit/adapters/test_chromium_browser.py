"""ChromiumBrowserAdapter: clear errors when the browser is missing; locality rule for requests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ddk.adapters import chromium_browser
from ddk.adapters.chromium_browser import (
    BrowserUnavailableError,
    ChromiumBrowserAdapter,
    is_local_url,
)


class _Launcher:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def launch(self, **_: Any) -> Any:
        raise self._error


class _FakePlaywright:
    def __init__(self, error: Exception) -> None:
        self.chromium = _Launcher(error)

    async def stop(self) -> None:
        return None


class _Starter:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def start(self) -> _FakePlaywright:
        return _FakePlaywright(self._error)


async def _async_none() -> None:
    return None


def _patch_playwright(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    monkeypatch.setattr(chromium_browser, "_playwright_factory", lambda: lambda: _Starter(error))


def _fake_browser_start(
    monkeypatch: pytest.MonkeyPatch,
    launched: list[dict[str, Any]],
    closed: list[str],
    *,
    fail_without_path: bool = False,
) -> None:
    class Browser:
        async def close(self) -> None:
            closed.append("browser")

    class Launcher:
        async def launch(self, **options: Any) -> Any:
            launched.append(options)
            if fail_without_path and options.get("executable_path") is None:
                raise RuntimeError("Executable doesn't exist at /nowhere")
            return Browser()

    async def stop() -> None:
        closed.append("playwright")

    class Starter:
        async def start(self) -> Any:
            return SimpleNamespace(chromium=Launcher(), stop=stop)

    monkeypatch.setattr(chromium_browser, "_playwright_factory", lambda: Starter)


class TestLocality:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:4173/",
            "http://localhost:3000/assets/app.js",
            "http://[::1]:8080/",
            "data:image/png;base64,AAAA",
            "blob:http://127.0.0.1:4173/abc",
            "about:blank",
        ],
    )
    def test_loopback_and_inline_urls_are_local(self, url: str) -> None:
        assert is_local_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "https://fonts.googleapis.com/css2?family=Inter",
            "http://203.0.113.9/x.png",
            "http://localhost.evil.example/",
            "http://127.0.0.1.evil.example/",
        ],
    )
    def test_everything_else_is_external(self, url: str) -> None:
        assert not is_local_url(url)


class TestUnavailable:
    async def test_missing_playwright_package_says_to_reinstall(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(sys.modules, "playwright.async_api", None)

        with pytest.raises(BrowserUnavailableError, match="reinstall ddalggak"):
            await ChromiumBrowserAdapter().capture_screenshot("http://127.0.0.1:1/", Path("x.png"))

    async def test_missing_browser_binary_names_the_fix(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_playwright(
            monkeypatch, RuntimeError("BrowserType.launch: Executable doesn't exist at /nowhere")
        )

        with pytest.raises(BrowserUnavailableError, match="ddk doctor --install-browser"):
            await ChromiumBrowserAdapter().capture_screenshot(
                "http://127.0.0.1:1/", tmp_path / "x.png"
            )

    async def test_missing_bundled_browser_falls_back_to_an_installed_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        launched: list[dict[str, Any]] = []

        class Launcher:
            async def launch(self, **options: Any) -> Any:
                launched.append(options)
                if options.get("executable_path") is None:
                    raise RuntimeError("Executable doesn't exist at /nowhere")
                return SimpleNamespace(close=_async_none)

        class Starter:
            async def start(self) -> Any:
                return SimpleNamespace(chromium=Launcher(), stop=_async_none)

        monkeypatch.setattr(chromium_browser, "_playwright_factory", lambda: Starter)
        chrome = tmp_path / "chrome"
        monkeypatch.setattr(chromium_browser, "find_system_browser", lambda: chrome)

        browser = await ChromiumBrowserAdapter()._ensure_browser()

        assert browser is not None
        assert [o.get("executable_path") for o in launched] == [None, str(chrome)]
        assert all(o["headless"] is True for o in launched)

    async def test_an_explicit_path_is_never_replaced_by_a_guess(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_playwright(
            monkeypatch, RuntimeError("BrowserType.launch: Executable doesn't exist at /mine")
        )
        monkeypatch.setattr(chromium_browser, "find_system_browser", lambda: tmp_path / "other")

        with pytest.raises(BrowserUnavailableError, match="/mine"):
            await ChromiumBrowserAdapter(executable_path="/mine").capture_screenshot(
                "http://127.0.0.1:1/", tmp_path / "x.png"
            )

    async def test_the_error_names_every_way_out_when_nothing_is_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_playwright(monkeypatch, RuntimeError("Executable doesn't exist at /nowhere"))
        monkeypatch.setattr(chromium_browser, "find_system_browser", lambda: None)

        with pytest.raises(BrowserUnavailableError) as raised:
            await ChromiumBrowserAdapter().capture_screenshot(
                "http://127.0.0.1:1/", tmp_path / "x.png"
            )

        message = str(raised.value)
        assert "ddk doctor --install-browser" in message
        assert "Chrome" in message and "DDK_CHROMIUM_PATH" in message

    async def test_other_launch_errors_are_not_disguised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _patch_playwright(monkeypatch, RuntimeError("kernel said no"))

        with pytest.raises(BrowserUnavailableError, match="kernel said no"):
            await ChromiumBrowserAdapter().get_console_errors("http://127.0.0.1:1/")

    async def test_close_without_use_is_a_no_op(self) -> None:
        adapter = ChromiumBrowserAdapter()

        await adapter.close()
        await adapter.close()

    def test_adapter_is_not_the_null_adapter(self) -> None:
        assert (
            SimpleNamespace(is_null=getattr(ChromiumBrowserAdapter(), "is_null", None)).is_null
            is False
        )


class TestProbe:
    async def test_it_starts_and_stops_playwrights_own_browser(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched: list[dict[str, Any]] = []
        closed: list[str] = []
        _fake_browser_start(monkeypatch, launched, closed)

        used = await ChromiumBrowserAdapter().probe()

        assert used == chromium_browser.PLAYWRIGHT_BUILD
        assert [o["headless"] for o in launched] == [True]
        assert closed == ["browser", "playwright"]

    async def test_it_names_the_installed_browser_it_fell_back_to(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        launched: list[dict[str, Any]] = []
        closed: list[str] = []
        _fake_browser_start(monkeypatch, launched, closed, fail_without_path=True)
        chrome = tmp_path / "chrome"
        monkeypatch.setattr(chromium_browser, "find_system_browser", lambda: chrome)

        assert await ChromiumBrowserAdapter().probe() == str(chrome)
        assert closed == ["browser", "playwright"]

    async def test_it_names_an_explicit_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _fake_browser_start(monkeypatch, [], [])
        mine = tmp_path / "mine"

        assert await ChromiumBrowserAdapter(executable_path=mine).probe() == str(mine)

    async def test_it_raises_when_nothing_starts_and_leaves_nothing_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        closed: list[str] = []
        _fake_browser_start(monkeypatch, [], closed, fail_without_path=True)
        monkeypatch.setattr(chromium_browser, "find_system_browser", lambda: None)

        with pytest.raises(BrowserUnavailableError, match="ddk doctor --install-browser"):
            await ChromiumBrowserAdapter().probe()

        assert closed == ["playwright"]

    async def test_the_browser_can_be_started_again_after_a_probe(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        launched: list[dict[str, Any]] = []
        _fake_browser_start(monkeypatch, launched, [])
        adapter = ChromiumBrowserAdapter()

        await adapter.probe()
        await adapter._ensure_browser()  # pyright: ignore[reportPrivateUsage]

        assert len(launched) == 2

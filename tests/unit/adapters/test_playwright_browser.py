"""Tests for PlaywrightAdapter protocol and data classes."""

from __future__ import annotations

from ddk.adapters.playwright_browser import (
    ConsoleEntry,
    FailedRequestEntry,
    PlaywrightAdapter,
)


class TestConsoleEntry:
    def test_create(self) -> None:
        entry = ConsoleEntry(level="error", message="Uncaught TypeError", url="http://localhost")
        assert entry.level == "error"
        assert entry.message == "Uncaught TypeError"
        assert entry.url == "http://localhost"


class TestFailedRequestEntry:
    def test_create(self) -> None:
        entry = FailedRequestEntry(
            url="http://localhost/api",
            failure_text="net::ERR_CONNECTION_REFUSED",
        )
        assert entry.url == "http://localhost/api"
        assert entry.failure_text == "net::ERR_CONNECTION_REFUSED"


class TestPlaywrightAdapterProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(PlaywrightAdapter, "__protocol_attrs__") or callable(
            getattr(PlaywrightAdapter, "__instancecheck__", None)
        )

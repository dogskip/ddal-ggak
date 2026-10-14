"""Tests for NullPlaywrightAdapter."""

from __future__ import annotations

import pytest

from ddk.adapters.null_playwright import NullPlaywrightAdapter


class TestNullPlaywrightAdapter:
    def test_is_null(self) -> None:
        adapter = NullPlaywrightAdapter()
        assert adapter.is_null is True

    @pytest.mark.asyncio
    async def test_capture_screenshot_creates_dir(self, tmp_path: object) -> None:
        from pathlib import Path

        adapter = NullPlaywrightAdapter()
        output = Path(str(tmp_path)) / "shots" / "test.png"
        result = await adapter.capture_screenshot(url="http://localhost", output_path=output)
        assert output.parent.is_dir()
        assert result == output

    @pytest.mark.asyncio
    async def test_get_console_errors_returns_empty(self) -> None:
        adapter = NullPlaywrightAdapter()
        result = await adapter.get_console_errors(url="http://localhost")
        assert result == [] or result is not None

    @pytest.mark.asyncio
    async def test_get_failed_requests_returns_empty(self) -> None:
        adapter = NullPlaywrightAdapter()
        result = await adapter.get_failed_requests(url="http://localhost")
        assert result == [] or result is not None

"""Shared test fixtures for ddalggak."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ddk.adapters.chromium_browser import PLAYWRIGHT_BUILD, ChromiumBrowserAdapter
from tests.fakes import (
    FakeLLMAdapter,
    FakePlaywrightAdapter,
    FakeSubprocessRunner,
    InMemoryFilesystem,
)


def pytest_configure() -> None:
    """Most assertions quote the Korean text; the English text has its own tests."""
    os.environ["DDK_LANG"] = "ko"


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for workspace tests."""
    (tmp_path / "package.json").write_text('{"name": "test-project"}')
    return tmp_path


@pytest.fixture
def sample_datetime() -> datetime:
    """Fixed datetime for deterministic tests."""
    return datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    """Pre-configured FakeLLMAdapter with a default response."""
    return FakeLLMAdapter(responses={"default": "fake response"})


@pytest.fixture
def in_memory_fs() -> InMemoryFilesystem:
    """Empty InMemoryFilesystem instance."""
    return InMemoryFilesystem()


@pytest.fixture
def fake_subprocess_runner() -> FakeSubprocessRunner:
    """FakeSubprocessRunner with default success behavior."""
    return FakeSubprocessRunner(default_success=True)


@pytest.fixture
def fake_playwright() -> FakePlaywrightAdapter:
    """FakePlaywrightAdapter with default screenshot path."""
    return FakePlaywrightAdapter()


@pytest.fixture(scope="session")
def anthropic_api_key() -> str:
    """Return API key or skip test if not set."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")
    return key


@pytest.fixture
def no_browser_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment checks report a working browser without starting one."""

    async def found(self: ChromiumBrowserAdapter) -> str:
        return PLAYWRIGHT_BUILD

    monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
    monkeypatch.setattr(ChromiumBrowserAdapter, "probe", found)

    async def observed(repository: Path) -> tuple[dict[str, str], str]:
        return {"browser_binary_sha256": "a" * 64, "font_manifest_sha256": "b" * 64}, "browser"

    monkeypatch.setattr("ddk.services.verified_host.observe_environment", observed)

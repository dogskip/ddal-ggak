"""Shared test fixtures for ddalggak."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.fakes import (
    FakeLLMAdapter,
    FakePlaywrightAdapter,
    FakeSubprocessRunner,
    InMemoryFilesystem,
)


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

"""Shared test fixtures for ddalggak."""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for workspace tests."""
    (tmp_path / "package.json").write_text('{"name": "test-project"}')
    return tmp_path


@pytest.fixture
def sample_datetime() -> datetime:
    """Fixed datetime for deterministic tests."""
    return datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

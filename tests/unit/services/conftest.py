"""Public evidence inputs shared by the live catalog checks."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def public_evidence_repo(tmp_path: Path) -> Path:
    """Copy real public artifacts while excluding optional internal documents."""
    project = Path(__file__).resolve().parents[3]
    for folder in ("benchmarks", "src", "tests", "docs"):
        shutil.copytree(
            project / folder,
            tmp_path / folder,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "design", "superpowers", "launch")
            if folder == "docs"
            else shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    return tmp_path

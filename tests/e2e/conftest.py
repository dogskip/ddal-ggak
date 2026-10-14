"""Shared set-up of the opt-in end-to-end tests (DDK_E2E=1)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from ddk.demo.runner import bundled_project


@pytest.fixture(scope="session")
def installed_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The bundled Vite project with its dependencies installed, once per session."""
    project = tmp_path_factory.mktemp("vite") / "app"
    shutil.copytree(bundled_project(), project)
    result = subprocess.run(
        ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(f"npm ci failed:\n{result.stderr[-800:]}")
    return project

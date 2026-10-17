"""Preparing a comparison must not silently grant project execution or overwrite output."""

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/paired_benchmark.py"


@pytest.mark.parametrize("command", ["oracle", "_worker"])
def test_execution_requires_explicit_trusted_local(command, tmp_path):
    if command == "oracle":
        arguments = [
            "oracle",
            "--task",
            "hyperapp-events",
            "--repo",
            str(tmp_path),
            "--seed",
            "1729",
            "--arm",
            "ddk",
        ]
    else:
        arguments = ["_worker", "hyperapp-events", str(tmp_path)]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True
    )
    assert result.returncode in (3, 4)
    assert list(tmp_path.iterdir()) == []


def test_preparation_preserves_existing_output(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    original = destination / "keep.txt"
    original.write_text("keep")
    arguments = [sys.executable, str(SCRIPT), "prepare", "--out", str(destination)]
    for source in ["click", "clsx", "hyperapp"]:
        arguments += ["--source", source + "=" + str(tmp_path)]
    result = subprocess.run(arguments, capture_output=True, text=True)
    assert result.returncode == 4
    assert original.read_text() == "keep"
    assert list(destination.iterdir()) == [original]

"""Public bilingual guides cover the same command surface and generated references."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
from typer.main import get_command

from ddk.cli import app

ROOT = Path(__file__).resolve().parents[2]
PAIRS = ["README", "docs/ONECLICK", "docs/USER-GUIDE", "docs/VERIFIED-CHANGES", "ROADMAP"]


def command_routes():
    def walk(command, path):
        if path:
            yield " ".join(["ddk", *path])
        for name, child in getattr(command, "commands", {}).items():
            yield from walk(child, [*path, name])

    return list(walk(get_command(app), []))


def structure(text):
    outside = []
    blocks = 0
    fenced = False
    for line in text.splitlines():
        if line.startswith("```"):
            fenced = not fenced
            blocks += int(fenced)
        if not fenced and (match := re.match(r"^(#{1,6}) ", line)):
            outside.append(len(match[1]))
    commands = {
        route
        for route in command_routes()
        if re.search(r"\b" + re.escape(route) + r"(?=[^a-z0-9-]|$)", text)
    }
    return outside, blocks, commands


@pytest.mark.parametrize("name", PAIRS)
def test_bilingual_structure_and_command_sets_match(name):
    english = structure((ROOT / (name + ".md")).read_text())
    korean = structure((ROOT / (name + ".ko.md")).read_text())
    assert english[:2] == korean[:2]
    assert english[2] == korean[2], {
        "english_only": sorted(english[2] - korean[2]),
        "korean_only": sorted(korean[2] - english[2]),
    }


@pytest.mark.parametrize(
    "script",
    [
        "generate_commands.py",
        "generate_claude_plugin.py",
        "generate_exit_codes.py",
        "generate_host_table.py",
        "check_import_graph.py",
    ],
)
def test_generated_references_are_current(script):
    arguments = [sys.executable, str(ROOT / "scripts" / script)]
    if script.startswith("generate_"):
        arguments.append("--check")
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

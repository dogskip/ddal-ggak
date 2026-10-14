"""`ddk run <image>` works without --prompt; the image alone is the brief."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ddk.cli import app
from ddk.cli.delivery import DEFAULT_PROMPT
from tests.fakes.images import write_png
from tests.fakes.runtime_services import stub_runtime_services

runner = CliRunner()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"react": "^18.3.0"}}), encoding="utf-8"
    )
    return repo


def _recorded_prompt(repo: Path) -> str:
    saved = repo / ".ddk" / "cases" / "C-001" / "reports" / "case-input.json"
    return json.loads(saved.read_text(encoding="utf-8"))["prompt"]


def test_prompt_is_optional(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    image = write_png(repo / "design.png")

    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: stub_runtime_services()):
        result = runner.invoke(app, ["run", str(image), "--repo", str(repo), "--json"])

    assert "Missing option" not in result.output
    assert _recorded_prompt(repo) == DEFAULT_PROMPT


def test_explicit_prompt_wins(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    image = write_png(repo / "design.png")

    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: stub_runtime_services()):
        runner.invoke(app, ["run", str(image), "-p", "make it dark", "--repo", str(repo), "--json"])

    assert _recorded_prompt(repo) == "make it dark"


def test_default_prompt_fits_the_input_limit() -> None:
    assert 0 < len(DEFAULT_PROMPT) <= 2000

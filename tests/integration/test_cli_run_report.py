"""`ddk run` leaves the evidence report next to the other reports."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.fakes.images import write_png
from tests.fakes.runtime_services import stub_runtime_services
from tests.public_contract import public_payload

runner = CliRunner()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text(
        json.dumps({"name": "x", "dependencies": {"react": "^18.3.0"}}), encoding="utf-8"
    )
    return repo


def _run(repo: Path) -> dict[str, object]:
    image = write_png(repo / "design.png")
    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: stub_runtime_services()):
        result = runner.invoke(app, ["run", str(image), "--repo", str(repo), "--json"])
    return public_payload(result.stdout)


def test_the_report_is_written_and_named_in_the_json(tmp_path: Path) -> None:
    repo = _repo(tmp_path)

    payload = _run(repo)

    page = repo / ".ddk" / "cases" / "C-001" / "reports" / "report.html"
    assert page.is_file()
    assert payload["report"] == str(page)
    assert payload["case_id"] == "C-001"


def test_the_human_output_names_the_report(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    image = write_png(repo / "design.png")

    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: stub_runtime_services()):
        result = runner.invoke(
            app, ["run", str(image), "--repo", str(repo)], env={"COLUMNS": "400"}
        )

    assert "report.html" in result.output


def test_a_report_that_cannot_be_written_does_not_fail_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _repo(tmp_path)

    def fail(case_path: Path) -> Path:
        raise OSError("disk full")

    monkeypatch.setattr("ddk.cli.delivery.write_report", fail)

    payload = _run(repo)

    assert payload["case_id"] == "C-001"
    assert "report" not in payload

"""`ddk report`: the evidence page of a saved case."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.fakes.case_folder import make_case

runner = CliRunner()


def test_writes_the_page_for_the_latest_case(tmp_path: Path) -> None:
    make_case(tmp_path, case_id="C-001")
    make_case(tmp_path, case_id="C-002")

    result = runner.invoke(app, ["report", "--repo", str(tmp_path)])

    page = tmp_path / ".ddk" / "cases" / "C-002" / "reports" / "report.html"
    assert result.exit_code == 0, result.output
    assert page.is_file()
    assert str(page) in result.output.replace("\n", "")
    assert not (tmp_path / ".ddk" / "cases" / "C-001" / "reports" / "report.html").exists()


def test_a_case_can_be_named(tmp_path: Path) -> None:
    make_case(tmp_path, case_id="C-001")
    make_case(tmp_path, case_id="C-002")

    result = runner.invoke(app, ["report", "--repo", str(tmp_path), "--case-id", "C-001"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".ddk" / "cases" / "C-001" / "reports" / "report.html").is_file()


def test_the_page_can_go_somewhere_else(tmp_path: Path) -> None:
    make_case(tmp_path)
    target = tmp_path / "share" / "case.html"

    result = runner.invoke(app, ["report", "--repo", str(tmp_path), "--output", str(target)])

    assert result.exit_code == 0, result.output
    assert target.is_file()


def test_a_blocked_case_still_gets_its_page_and_a_zero_exit(tmp_path: Path) -> None:
    make_case(tmp_path, decision="blocked", ssims=(0.8,))

    result = runner.invoke(app, ["report", "--repo", str(tmp_path)])

    assert result.exit_code == 0, result.output


def test_no_cases_is_an_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["report", "--repo", str(tmp_path)])

    assert result.exit_code == 1
    assert "ddk run" in result.output


def test_a_case_without_a_verdict_is_an_error(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    (case / "reports" / "release-decision.json").unlink()

    result = runner.invoke(app, ["report", "--repo", str(tmp_path)])

    assert result.exit_code == 1
    assert "release-decision.json" in result.output.replace("\n", "")
    assert not (case / "reports" / "report.html").exists()


def test_open_hands_the_page_to_the_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_case(tmp_path)
    opened: list[str] = []
    monkeypatch.setattr("ddk.cli.evidence.webbrowser.open", lambda url: opened.append(url))

    result = runner.invoke(app, ["report", "--repo", str(tmp_path), "--open"])

    assert result.exit_code == 0, result.output
    page = tmp_path / ".ddk" / "cases" / "C-001" / "reports" / "report.html"
    assert opened == [page.resolve().as_uri()]


def test_without_open_no_browser_is_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_case(tmp_path)
    opened: list[str] = []
    monkeypatch.setattr("ddk.cli.evidence.webbrowser.open", lambda url: opened.append(url))

    runner.invoke(app, ["report", "--repo", str(tmp_path)])

    assert opened == []


def test_the_page_follows_the_language(tmp_path: Path) -> None:
    make_case(tmp_path)

    runner.invoke(app, ["report", "--repo", str(tmp_path)], env={"DDK_LANG": "en"})

    page = tmp_path / ".ddk" / "cases" / "C-001" / "reports" / "report.html"
    assert '<html lang="en">' in page.read_text(encoding="utf-8")


def test_a_place_that_cannot_be_written_is_an_error(tmp_path: Path) -> None:
    make_case(tmp_path)
    folder = tmp_path / "folder"
    folder.mkdir()

    result = runner.invoke(app, ["report", "--repo", str(tmp_path), "--output", str(folder)])

    assert result.exit_code == 1
    assert "보고서를 쓸 수 없습니다" in result.output

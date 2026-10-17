"""A malformed setting stops the command with a message that names it."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-test")


def test_out_of_range_setting_is_named_with_its_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_SSIM_THRESHOLD", "5")

    result = runner.invoke(app, ["preflight"])

    assert result.exit_code == 3
    assert "DDK_SSIM_THRESHOLD" in result.output
    assert "5" in result.output


def test_non_numeric_setting_is_named(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_COST_CAP_USD", "lots")

    result = runner.invoke(app, ["preflight"])

    assert result.exit_code == 3
    assert "DDK_COST_CAP_USD" in result.output


def test_the_message_never_echoes_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-secret-value")
    monkeypatch.setenv("DDK_COST_CAP_USD", "lots")

    result = runner.invoke(app, ["preflight"])

    assert "sk-ant-secret-value" not in result.output


@pytest.mark.usefixtures("no_browser_start")
def test_doctor_still_runs_and_reports_the_setting_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DDK_SSIM_THRESHOLD", "5")

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 1
    assert "Python" in result.output
    assert "설정 값" in result.output


def test_version_ignores_a_broken_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_SSIM_THRESHOLD", "5")

    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert result.output.startswith("ddk")


@pytest.mark.usefixtures("no_browser_start")
def test_a_valid_dotenv_file_is_read(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DDK_ANTHROPIC_API_KEY=sk-ant-from-dotenv\n")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["doctor"])

    assert "✅ provider-credentials" in result.output

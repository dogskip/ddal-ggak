"""CLI integration tests for serve/install commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ddk.cli import app

runner = CliRunner()


def test_install_detect_reports_project_tools(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()

    with patch("ddk.installer.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["install", "--detect"])

    assert result.exit_code == 0, result.stdout
    assert "claude" in result.stdout
    assert "cursor" in result.stdout


def test_install_claude_writes_templates_and_settings(tmp_path: Path) -> None:
    with patch("ddk.installer.Path.cwd", return_value=tmp_path):
        result = runner.invoke(app, ["install", "--claude"])

    assert result.exit_code == 0, result.stdout
    assert (tmp_path / ".claude" / "commands" / "ddk" / "design.md").exists()
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_serve_cli_delegates_to_server_entrypoint() -> None:
    with patch("ddk.server.run_server") as run_mock:
        result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0, result.stdout
    run_mock.assert_called_once_with()

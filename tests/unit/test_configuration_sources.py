"""Flags, environment, repository files and defaults have a fixed priority."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.models.config import DdalggakConfig


@pytest.fixture(autouse=True)
def clean_settings_env(monkeypatch):
    for name in DdalggakConfig.model_fields:
        monkeypatch.delenv("DDK_" + name.upper(), raising=False)
    for name in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(name, raising=False)


def test_all_layers_and_origins(tmp_path, monkeypatch):
    from ddk.models.config import observe_settings

    (tmp_path / "ddk.toml").write_text("[settings]\ncost_cap_usd = 10\n")
    (tmp_path / ".env").write_text("DDK_COST_CAP_USD=20\n")
    monkeypatch.setenv("DDK_COST_CAP_USD", "30")
    config, sources = observe_settings(tmp_path, {"cost_cap_usd": 40})
    assert config.cost_cap_usd == 40 and sources["cost_cap_usd"] == "flag"
    config, sources = observe_settings(tmp_path)
    assert config.cost_cap_usd == 30 and sources["cost_cap_usd"] == "environment"
    monkeypatch.delenv("DDK_COST_CAP_USD")
    config, sources = observe_settings(tmp_path)
    assert config.cost_cap_usd == 20 and sources["cost_cap_usd"] == "dotenv"
    (tmp_path / ".env").unlink()
    config, sources = observe_settings(tmp_path)
    assert config.cost_cap_usd == 10 and sources["cost_cap_usd"] == "toml"
    (tmp_path / "ddk.toml").unlink()
    config, sources = observe_settings(tmp_path)
    assert config.cost_cap_usd == 2 and sources["cost_cap_usd"] == "default"


def test_environment_alias_beats_prefixed_dotenv_secret(tmp_path, monkeypatch):
    from ddk.models.config import observe_settings

    (tmp_path / ".env").write_text("DDK_ANTHROPIC_API_KEY=from-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-environment")
    config, sources = observe_settings(tmp_path)
    assert config.anthropic_api_key == "from-environment"
    assert sources["anthropic_api_key"] == "environment"


def test_repository_settings_ignore_the_callers_dotenv(tmp_path, monkeypatch):
    from ddk.models.config import observe_settings

    project = tmp_path / "project"
    project.mkdir()
    (tmp_path / ".env").write_text("DDK_COST_CAP_USD=bad-cwd\n")
    (project / ".env").write_text("DDK_COST_CAP_USD=7\n")
    monkeypatch.chdir(tmp_path)
    assert observe_settings(project)[0].cost_cap_usd == 7


def test_invalid_lower_priority_value_can_be_overridden(tmp_path, monkeypatch):
    from ddk.models.config import observe_settings

    (tmp_path / "ddk.toml").write_text('[settings]\ncost_cap_usd = "invalid"\n')
    monkeypatch.setenv("DDK_COST_CAP_USD", "also-invalid")
    config, sources = observe_settings(tmp_path, {"cost_cap_usd": 3})
    assert config.cost_cap_usd == 3 and sources["cost_cap_usd"] == "flag"


def test_config_list_masks_secrets_and_reports_origins(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-value-never-output")
    (tmp_path / "ddk.toml").write_text("[settings]\ncost_cap_usd = 9\n")
    result = CliRunner().invoke(app, ["config", "list", "--repo", str(tmp_path), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    values = payload["data"]["settings"]
    assert values["cost_cap_usd"] == {"value": 9, "source": "toml"}
    assert values["anthropic_api_key"] == {"value": "***", "source": "environment"}
    assert "private-value-never-output" not in result.output


def test_explicit_global_option_overrides_environment_and_records_origin(tmp_path):
    result = CliRunner().invoke(
        app,
        ["--log-level", "DEBUG", "config", "list", "--repo", str(tmp_path), "--json"],
        env={"DDK_LOG_LEVEL": "ERROR"},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["data"]["settings"]["log_level"] == {
        "value": "DEBUG",
        "source": "flag",
    }

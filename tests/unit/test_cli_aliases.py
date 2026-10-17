"""Deprecated names preserve behavior and keep warnings off JSON stdout."""

from __future__ import annotations

import json

from typer.main import get_command
from typer.testing import CliRunner

from ddk.cli import app
from tests.unit.test_cli_verified import Service


def test_case_paths_and_case_ids_have_distinct_primary_options():
    commands = get_command(app)
    verify = commands.commands["change"].commands["verify"]
    path = next(p for p in verify.params if p.name == "case")
    assert path.opts == ["--case-file", "--case"]
    for command in [
        commands.commands["up"],
        commands.commands["probe"],
        commands.commands["change"].commands["gate"],
    ]:
        parameter = next(p for p in command.params if p.name == "case_id")
        assert parameter.opts == ["--case-id", "--case"]
    assert all("-o" not in getattr(p, "opts", []) for p in commands.params)


def test_case_file_alias_warns_without_changing_the_verification_request(tmp_path, monkeypatch):
    service = Service()
    monkeypatch.setattr("ddk.cli.verified._service", lambda repo: service)
    case = tmp_path / "case.json"
    case.write_text("{}")
    for flag in ["--case-file", "--case"]:
        result = CliRunner().invoke(app, ["change", "verify", flag, str(case), "--json"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["data"]["decision"] == "ready"
        assert ("--case-file" in result.stderr) == (flag == "--case")
    assert service.calls[0] == service.calls[2]


def test_top_level_init_is_a_warning_alias(tmp_path):
    for prefix in [["init"], ["change", "init"]]:
        result = CliRunner().invoke(app, [*prefix, "--repo", str(tmp_path), "--dry-run", "--json"])
        assert result.exit_code == 1, result.output
        assert json.loads(result.stdout)["data"]["dry_run"]
        assert ("change init" in result.stderr) == (prefix == ["init"])


def test_preflight_delegates_to_the_same_doctor_contract(tmp_path, monkeypatch):
    async def readiness(repository):
        return {"status": "ready", "read_only": True, "checks": []}

    monkeypatch.setattr("ddk.services.verified_host.readiness", readiness)
    results = []
    for command in ["preflight", "doctor"]:
        result = CliRunner().invoke(app, [command, "--repo", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        results.append(json.loads(result.stdout)["data"])
        assert ("preflight" in result.stderr) == (command == "preflight")
    assert results[0] == results[1]

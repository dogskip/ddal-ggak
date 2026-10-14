from __future__ import annotations

import json

from typer.testing import CliRunner

from ddk.cli import app
from tests.unit.test_case_bootstrapper import setup_repo

runner = CliRunner()


def test_up_dry_run_reports_missing_acceptance_without_writes(tmp_path):
    setup_repo(tmp_path)
    result = runner.invoke(
        app, ["up", "Fix heading", "--repo", str(tmp_path), "--dry-run", "--json"]
    )
    assert result.exit_code == 0, result.output
    answer = json.loads(result.stdout)
    assert answer["dry_run"] and answer["status"] == "blocked"
    assert not (tmp_path / ".ddk").exists()


def test_init_alias_and_change_init_share_contract(tmp_path):
    setup_repo(tmp_path)
    for command in (["init"], ["change", "init"]):
        result = runner.invoke(
            app,
            [*command, "--repo", str(tmp_path), "--request", "Fix heading", "--dry-run", "--json"],
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["status"] == "blocked"


def test_probe_and_reindex_are_discoverable():
    for command in (["probe"], ["change", "reindex"]):
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, result.output

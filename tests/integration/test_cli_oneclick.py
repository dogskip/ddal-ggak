from __future__ import annotations

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.public_contract import public_payload
from tests.unit.test_case_bootstrapper import setup_repo

runner = CliRunner()


def test_up_dry_run_reports_missing_acceptance_without_writes(tmp_path):
    setup_repo(tmp_path)
    result = runner.invoke(
        app, ["up", "Fix heading", "--repo", str(tmp_path), "--dry-run", "--json"]
    )
    assert result.exit_code == 1, result.output
    answer = public_payload(result.stdout)
    assert answer["dry_run"] and answer["status"] == "blocked"
    assert not (tmp_path / ".ddk").exists()


def test_init_alias_and_change_init_share_contract(tmp_path):
    setup_repo(tmp_path)
    for command in (["init"], ["change", "init"]):
        result = runner.invoke(
            app,
            [*command, "--repo", str(tmp_path), "--request", "Fix heading", "--dry-run", "--json"],
        )
        assert result.exit_code == 1, result.output
        assert public_payload(result.stdout)["status"] == "blocked"


def test_probe_and_reindex_are_discoverable():
    for command in (["probe"], ["change", "reindex"]):
        result = runner.invoke(app, [*command, "--help"])
        assert result.exit_code == 0, result.output


@pytest.mark.parametrize("options", [[], ["--dry-run"], ["--json"], ["--dry-run", "--json"]])
def test_doctor_uses_the_same_readiness_and_blocked_exit(tmp_path, monkeypatch, options):
    from ddk.services import verified_host

    calls = []

    async def readiness(repository):
        calls.append(repository)
        return {
            "status": "blocked",
            "read_only": True,
            "checks": [{"name": "required-test-tool", "status": "blocked", "action": "fix-tool"}],
        }

    monkeypatch.setattr(verified_host, "readiness", readiness)
    result = runner.invoke(app, ["doctor", "--repo", str(tmp_path), *options])
    assert result.exit_code == 1, result.output
    assert calls == [tmp_path]
    assert "required-test-tool" in result.output and "fix-tool" in result.output
    if "--json" in options:
        assert public_payload(result.stdout)["status"] == "blocked"


def test_doctor_dry_run_never_installs_even_when_requested(tmp_path, monkeypatch):
    from ddk.cli import workspace
    from ddk.services import verified_host

    async def readiness(repository):
        return {"status": "ready", "checks": [], "read_only": True}

    monkeypatch.setattr(verified_host, "readiness", readiness)
    monkeypatch.setattr(workspace, "install_chromium", lambda: pytest.fail("dry run installed"))
    result = runner.invoke(app, ["doctor", "--dry-run", "--install-browser", "--json"])
    assert result.exit_code == 0, result.output
    assert public_payload(result.stdout)["read_only"]

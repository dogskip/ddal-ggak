"""CLI uses the real service, engine and store; evaluator observations are synthetic."""

from __future__ import annotations

import json
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from ddk.cli import app, verified
from ddk.models.verified_change import record_digest
from ddk.services.verified_change_service import VerifiedChangeService
from tests.unit.services.test_managed_application import ready_store
from tests.unit.test_verified_change_engine import RUN_ID, Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario

runner = CliRunner()
APPLY_ID = "00000000-0000-4000-8000-000000000099"


def test_cli_import_verify_status_replay_uses_one_real_engine(scenario, tmp_path, monkeypatch):
    original, case, baseline, candidate = scenario
    evaluator = Evaluator()
    repository = tmp_path / "new-repository"
    monkeypatch.setattr(
        verified, "_service", lambda path: VerifiedChangeService(path, evaluator=evaluator)
    )
    definition = original.path_for("case", case["case_id"]) / "case.json"
    requirements = tmp_path / "requirements.json"
    requirements.write_text('{"src/App.tsx":["R2"]}')
    args = [
        "change",
        "verify",
        "--repo",
        str(repository),
        "--case",
        str(definition),
        "--inputs",
        str(definition.parent / "inputs"),
        "--baseline",
        str(baseline),
        "--candidate",
        str(candidate),
        "--run-id",
        RUN_ID,
        "--change-requirements",
        str(requirements),
        "--json",
    ]

    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    result = json.loads(first.stdout)
    assert result["decision"] == "ready"
    assert result["model_calls"] == []
    assert [request.phase for request in evaluator.requests] == ["baseline", "candidate"]

    status = runner.invoke(
        app,
        [
            "change",
            "status",
            "--repo",
            str(repository),
            "--run-id",
            RUN_ID,
            "--json",
        ],
    )
    replay = runner.invoke(app, args)
    assert status.exit_code == replay.exit_code == 0, status.output + replay.output
    assert json.loads(status.stdout) == json.loads(replay.stdout) == result
    assert len(evaluator.requests) == 2
    assert (baseline / "src/App.tsx").read_bytes() == b"before"
    assert (candidate / "src/App.tsx").read_bytes() == b"after"


def test_cli_status_export_apply_recover_reach_real_owned_storage(tmp_path):
    repository = tmp_path / "repository"
    store, run = ready_store(repository)
    common = ["--repo", str(repository), "--json"]

    status = runner.invoke(app, ["change", "status", "--run-id", run["run_id"], *common])
    assert status.exit_code == 0, status.output
    assert json.loads(status.stdout) == run

    destination = tmp_path / "public.zip"
    export = runner.invoke(
        app,
        [
            "change",
            "export",
            "--run-id",
            run["run_id"],
            "--destination",
            str(destination),
            *common,
        ],
    )
    assert export.exit_code == 0, export.output
    assert json.loads(export.stdout)["included_artifacts"] == []
    with ZipFile(destination) as archive:
        assert archive.namelist() == ["report.json"]
        assert json.loads(archive.read("report.json"))["decision"] == "ready"

    apply = runner.invoke(
        app,
        [
            "change",
            "apply",
            "--apply-id",
            APPLY_ID,
            "--case-id",
            run["case_id"],
            "--run-id",
            run["run_id"],
            "--run-sha256",
            record_digest(run),
            "--changes-sha256",
            record_digest(run["changes"]),
            "--confirm-local-storage",
            "--confirm-quiescence",
            *common,
        ],
    )
    assert apply.exit_code == 0, apply.output
    applied = json.loads(apply.stdout)
    assert applied["state"] == "applied"
    assert (repository / "src/App.tsx").read_bytes() == b"new\n"
    assert store.load_apply(APPLY_ID) == applied

    recovery = runner.invoke(
        app,
        [
            "change",
            "recover",
            "--apply-id",
            APPLY_ID,
            "--confirm-local-storage",
            "--confirm-same-host",
            "--confirm-quiescence",
            *common,
        ],
    )
    assert recovery.exit_code == 0, recovery.output
    assert json.loads(recovery.stdout) == applied
    assert (repository / "src/App.tsx").read_bytes() == b"new\n"


def test_cli_corrupted_saved_artifact_is_an_error_without_replay(tmp_path):
    store, run = ready_store(tmp_path)
    artifact = store.path_for("run", run["run_id"]) / run["artifacts"][0]["path"]
    artifact.write_bytes(b"corrupt")
    result = runner.invoke(
        app,
        [
            "change",
            "status",
            "--repo",
            str(tmp_path),
            "--run-id",
            run["run_id"],
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"]
    assert artifact.read_bytes() == b"corrupt"
    assert (tmp_path / "src/App.tsx").read_bytes() == b"old\n"


def test_cli_host_permission_cannot_lower_an_isolated_case(scenario, monkeypatch):
    store, case, baseline, candidate = scenario
    evaluator = Evaluator()
    monkeypatch.setattr(
        verified, "_service", lambda path: VerifiedChangeService(path, evaluator=evaluator)
    )
    result = runner.invoke(
        app,
        [
            "change",
            "verify",
            "--repo",
            str(store.repository),
            "--case-id",
            case["case_id"],
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--run-id",
            RUN_ID,
            "--trusted-local",
            "--json",
        ],
    )
    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"] == "assurance_mismatch"
    assert evaluator.requests == []


@pytest.mark.parametrize("alias_position", ["repository", "ancestor"])
def test_cli_preserves_repository_alias_rejection(tmp_path, alias_position):
    repository = tmp_path / "actual" / "parent" / "repository"
    _, run = ready_store(repository)
    alias = tmp_path / "alias"
    alias.symlink_to(repository if alias_position == "repository" else repository.parents[1])
    selected = alias if alias_position == "repository" else alias / "parent" / "repository"

    result = runner.invoke(
        app,
        ["change", "status", "--repo", str(selected), "--run-id", run["run_id"], "--json"],
    )

    assert result.exit_code == 2, result.output
    assert json.loads(result.stdout)["error"]["code"]
    assert (repository / "src/App.tsx").read_bytes() == b"old\n"

"""The real CLI runs fixed headless checks only after an explicit local grant."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.models.verified_change import canonical_json
from ddk.services.source_snapshot import capture_source
from tests.e2e.test_verified_browser import settings as settings
from tests.e2e.test_verified_evaluator import scenario
from tests.public_contract import public_payload
from tests.unit.test_verified_change_engine import RUN_ID

pytestmark = pytest.mark.playwright
runner = CliRunner()


def test_real_cli_verification_requires_authority_and_retains_headless_evidence(
    tmp_path, settings, monkeypatch
):
    for variable in ("ANTHROPIC_API_KEY", "DDK_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
    case, store, originals = scenario(tmp_path, settings)
    requirements = tmp_path / "requirements.json"
    requirements.write_text('{"index.html":["target"]}')
    args = [
        "change",
        "verify",
        "--repo",
        str(store.repository),
        "--case-id",
        case["case_id"],
        "--baseline",
        str(tmp_path / "baseline"),
        "--candidate",
        str(tmp_path / "candidate"),
        "--run-id",
        RUN_ID,
        "--change-requirements",
        str(requirements),
        "--json",
    ]

    denied = runner.invoke(app, args)
    assert denied.exit_code == 3, denied.output
    assert public_payload(denied.stdout)["error"]["code"] == "trusted_local_confirmation_required"
    assert not store.path_for("run", RUN_ID).exists()

    result = runner.invoke(app, [*args, "--trusted-local"])
    assert result.exit_code == 0, result.output
    record = public_payload(result.stdout)
    assert record["decision"] == "ready"
    assert record["assurance"] == "trusted-local"
    assert record["model_calls"] == []
    assert record["integrity"]["cleanup_complete"]
    assert {result["phase"] for result in record["results"]} == {"baseline", "candidate"}
    browser_results = [result for result in record["results"] if result["check_id"] != "tests"]
    assert all(result["evidence_origin"] == "trusted-observer" for result in browser_results)
    assert all(result["artifact_ids"] for result in browser_results)
    assert all(
        result["status"] == "passed" for result in browser_results if result["phase"] == "candidate"
    )

    run_dir = store.path_for("run", RUN_ID)
    observations = []
    for artifact in record["artifacts"]:
        payload = (run_dir / artifact["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]
        if artifact["kind"] == "data":
            observations.append(json.loads(payload))
    assert len(observations) == 4
    assert all(observation["cleanup_complete"] for observation in observations)
    assert any(artifact["kind"] == "screenshot" for artifact in record["artifacts"])
    assert not [
        error
        for observation in observations
        for error in observation["errors"]
        if error["code"] in {"console_error", "page_error"}
    ]
    preservation = {
        name: {"before": snapshot.tree_sha256, "after": capture_source(tmp_path / name).tree_sha256}
        for name, snapshot in originals.items()
    }
    assert all(item["before"] == item["after"] for item in preservation.values())
    assert store.status(RUN_ID) == record

    destination = os.environ.get("DDK_FUNCTIONAL_EVIDENCE_DIR")
    if destination:
        output = Path(destination).resolve() / "cli"
        output.mkdir(parents=True, exist_ok=True)
        for artifact in record["artifacts"]:
            target = output / artifact["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run_dir / artifact["path"], target)
        (output / "run.json").write_bytes(canonical_json(record))
        (output / "originals.json").write_bytes(canonical_json(preservation))

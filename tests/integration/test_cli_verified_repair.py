"""CLI repair uses real storage, reservations and independent injected observations."""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest
from typer.testing import CliRunner

from ddk.cli import app, verified
from ddk.services.verified_change_service import VerifiedChangeService
from tests.unit.test_verified_budget import price
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import REPAIR_ID, ObservingEvaluator, answer
from tests.unit.test_verified_repair import blocked as blocked

runner = CliRunner()


def arguments(blocked, tmp_path):
    (store, _, baseline, candidate), source = blocked
    pricing = tmp_path / "price.json"
    pricing.write_text(json.dumps(asdict(price(source))))
    return [
        "change",
        "repair",
        "--repo",
        str(store.repository),
        "--source-run-id",
        source["run_id"],
        "--baseline",
        str(baseline),
        "--candidate",
        str(candidate),
        "--run-id",
        REPAIR_ID,
        "--price",
        str(pricing),
        "--input-token-limit",
        "4096",
        "--output-token-limit",
        "512",
        "--json",
    ]


def test_repair_command_requires_grant_and_emits_one_json_record(blocked, tmp_path, monkeypatch):
    (store, _, _, _), source = blocked
    attempts = []

    async def provider(request):
        attempts.append(request)
        return answer()

    monkeypatch.setattr(verified, "_repair_provider", lambda: provider)
    monkeypatch.setattr(
        verified,
        "_service",
        lambda path: VerifiedChangeService(path, evaluator=ObservingEvaluator()),
    )
    args = arguments(blocked, tmp_path)
    refused = runner.invoke(app, args)
    assert refused.exit_code == 2, refused.output
    assert json.loads(refused.stdout)["error"]["code"] == "provider_confirmation_required"
    assert not attempts
    first = runner.invoke(app, [*args, "--confirm-provider"])
    assert first.exit_code == 0, first.output
    record = json.loads(first.stdout)
    assert record["decision"] == "ready"
    assert record["operation"] == "repair"
    assert record["source_run_id"] == source["run_id"]
    monkeypatch.setattr(
        verified, "_repair_provider", lambda: pytest.fail("replay must not build a provider")
    )
    replay = runner.invoke(app, [*args, "--confirm-provider"])
    assert replay.exit_code == 0, replay.output
    assert json.loads(replay.stdout) == record
    assert len(attempts) == 1
    assert store.run(REPAIR_ID) == record

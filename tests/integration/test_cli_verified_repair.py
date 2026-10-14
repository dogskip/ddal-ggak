"""CLI repair uses real storage, reservations and independent injected observations."""

from __future__ import annotations

import json
from dataclasses import asdict, replace

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


@pytest.mark.parametrize("kind", ["anthropic", "openai-compatible", "claude-cli", "codex-cli"])
def test_all_repair_entry_points_select_the_requested_provider(
    blocked, tmp_path, monkeypatch, kind
):
    from ddk.adapters import verified_provider

    (store, _, _, _), source = blocked
    quote = replace(price(source), provider=kind)
    attempts = []

    async def provider(request):
        attempts.append(request)
        return replace(answer(), provider=kind)

    monkeypatch.setattr(verified_provider, "provider_for", lambda selected, endpoint=None: provider)
    monkeypatch.setattr(verified, "_repair_provider", lambda: provider)
    monkeypatch.setattr(
        verified,
        "_service",
        lambda path: VerifiedChangeService(path, evaluator=ObservingEvaluator()),
    )
    args = arguments(blocked, tmp_path)
    pricing = tmp_path / "price.json"
    pricing.write_text(json.dumps(asdict(quote)))
    args += ["--provider", kind, "--confirm-provider"]
    if kind == "openai-compatible":
        args += ["--endpoint", "http://127.0.0.1:1234/v1"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["decision"] == "ready"
    assert len(attempts) == 1
    assert store.run(REPAIR_ID)["model_calls"][0]["state"] == "settled"


def test_change_repair_can_use_case_bound_default_price(blocked, tmp_path, monkeypatch):
    from ddk.adapters import verified_provider

    (store, case, _, _), _ = blocked
    quotations = []

    def built_in(model, evaluator):
        quotations.append((model, evaluator))
        return price(case)

    async def provider(request):
        return answer()

    monkeypatch.setattr(verified_provider, "default_price", built_in)
    monkeypatch.setattr(verified, "_repair_provider", lambda: provider)
    monkeypatch.setattr(
        verified,
        "_service",
        lambda path: VerifiedChangeService(path, evaluator=ObservingEvaluator()),
    )
    args = arguments(blocked, tmp_path)
    offset = args.index("--price")
    del args[offset : offset + 2]
    result = runner.invoke(app, [*args, "--confirm-provider"])
    assert result.exit_code == 0, result.output
    assert quotations == [("claude-sonnet-5-5", case["evaluator_sha256"])]
    assert store.run(REPAIR_ID)["decision"] == "ready"

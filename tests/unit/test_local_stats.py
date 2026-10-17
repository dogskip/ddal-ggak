"""Local aggregates preserve unknown charges and never emit stored free text."""

from __future__ import annotations

import json
import socket

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.unit.test_verified_budget import call, result, setup
from tests.unit.test_verified_budget import prepared as prepared


def legacy(repository, calls):
    path = repository / ".ddk/cases/C-001/reports/llm-calls.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(calls))
    return path


def invoke(repository):
    response = CliRunner().invoke(app, ["stats", "--repo", str(repository), "--json"])
    return response, json.loads(response.stdout)


def test_empty_stats_do_not_create_storage_or_contact_the_network(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network contact")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    response, payload = invoke(tmp_path)
    assert response.exit_code == 0, response.output
    assert payload["data"]["recorded_total_micro_usd"] == 0
    assert payload["data"]["calls"] == 0
    assert list(tmp_path.iterdir()) == []


def test_legacy_costs_are_aggregated_without_any_free_text(tmp_path):
    legacy(
        tmp_path,
        [
            {
                "sequence": 1,
                "status": "ok",
                "cost_usd": 0.012345,
                "input_tokens": 12,
                "output_tokens": 3,
                "model": "PRIVATE-MODEL-CANARY",
                "prompt": "PRIVATE-PROMPT-CANARY",
                "source": "PRIVATE-SOURCE-CANARY",
                "error": "PRIVATE-ERROR-CANARY",
            }
        ],
    )
    response, payload = invoke(tmp_path)
    assert response.exit_code == 0, response.output
    assert payload["data"]["recorded_total_micro_usd"] == 12345
    assert payload["data"]["input_tokens"] == 12
    assert "PRIVATE-" not in response.output


@pytest.mark.parametrize("change", [{"status": "error"}, {"cost_usd": None}, {}])
def test_unknown_legacy_cost_is_never_zero(tmp_path, change):
    legacy(tmp_path, [{"sequence": 1, "status": "error", **change}])
    response, payload = invoke(tmp_path)
    assert response.exit_code == 1
    assert payload["data"]["recorded_total_micro_usd"] is None
    assert payload["data"]["unknown_calls"] == 1


async def test_verified_settlement_and_unknown_calls_use_canonical_records(prepared):
    from ddk.services.verified_budget import RunBudget

    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    await call(budget, run)
    response, payload = invoke(store.repository)
    assert response.exit_code == 0, response.output
    assert payload["data"]["recorded_total_micro_usd"] == 1
    assert payload["data"]["reserved_micro_usd"] == 3
    assert payload["data"]["pending_runs"] == 1

    async def unknown():
        return result(None)

    await call(budget, run, unknown)
    response, payload = invoke(store.repository)
    assert response.exit_code == 1, response.output
    assert payload["data"]["recorded_total_micro_usd"] is None
    assert payload["data"]["known_cost_micro_usd"] == 1
    assert payload["data"]["calls"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        '[{"sequence":1,"status":"ok","cost_usd":-1}]',
        '[{"sequence":1,"status":"ok","cost_usd":NaN}]',
        "not-json",
    ],
)
def test_invalid_metadata_never_becomes_a_successful_total(tmp_path, payload):
    path = legacy(tmp_path, [])
    path.write_text(payload)
    response, output = invoke(tmp_path)
    assert response.exit_code == 5
    assert output["error"]["code"] == "invalid_cost_records"


def test_linked_storage_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".ddk").symlink_to(outside, target_is_directory=True)
    response, _ = invoke(tmp_path)
    assert response.exit_code == 5
    assert list(outside.iterdir()) == []


def test_directory_scan_has_a_fixed_limit(tmp_path, monkeypatch):
    from ddk.services import local_stats

    for name in ["C-001", "C-002"]:
        (tmp_path / ".ddk/cases" / name).mkdir(parents=True)
    monkeypatch.setattr(local_stats, "MAX_RECORDS", 1)
    response, _ = invoke(tmp_path)
    assert response.exit_code == 5


async def test_modified_usage_evidence_cannot_supply_a_total(prepared):
    from ddk.services.verified_budget import RunBudget

    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    outcome = await call(budget, run)
    saved = store.pending_run(run["run_id"])
    item = next(
        a
        for a in saved["artifacts"]
        if a["artifact_id"] == "usage-" + outcome.call_record["call_id"]
    )
    (store.path_for("run", run["run_id"]) / item["path"]).write_text("PRIVATE-BROKEN-USAGE")
    response, output = invoke(store.repository)
    assert response.exit_code == 5
    assert output["data"] == {}
    assert "PRIVATE-BROKEN-USAGE" not in response.output


def test_missing_legacy_metadata_is_unknown(tmp_path):
    (tmp_path / ".ddk/cases/C-001").mkdir(parents=True)
    response, payload = invoke(tmp_path)
    assert response.exit_code == 1
    assert payload["data"]["recorded_total_micro_usd"] is None
    assert payload["data"]["input_tokens"] is None


def test_duplicate_calls_do_not_reduce_or_inflate_the_total(tmp_path):
    call = {"sequence": 1, "status": "ok", "cost_usd": 0.01}
    legacy(tmp_path, [call, call])
    response, _ = invoke(tmp_path)
    assert response.exit_code == 5

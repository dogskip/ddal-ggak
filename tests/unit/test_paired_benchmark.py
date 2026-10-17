"""Paired receipts retain failures and bind independent observations."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.models.verified_change import canonical_json
from tests.unit.test_verified_change_store import prepared_run
from tests.unit.test_verified_change_store import records as records


def test_no_measurements_cannot_calibrate_a_baseline(tmp_path):
    result = CliRunner().invoke(app, ["bench", "--json"])
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)["data"]
    assert data["status"] == "unmeasured" and data["calibrated"] is False
    assert data["repositories"] == 3 and data["expected_records"] == 18
    assert data["measured_records"] == 0
    baseline = Path(__file__).resolve().parents[2] / "benchmarks/gsd-baseline.json"
    assert json.loads(baseline.read_text())["calibrated"] is False


@pytest.fixture
def receipts(tmp_path, records):
    from ddk.services.paired_benchmark import cohort_hash, corpus
    from ddk.services.verified_change_store import VerifiedChangeStore

    plan, digest = corpus()
    cohort = {
        "host": "recorded-test-host",
        "host_version": "1.0",
        "model": "recorded-model",
        "model_revision": "fixed",
        "ddk_commit": "a" * 40,
        "environment_sha256": "b" * 64,
        "permission_policy_sha256": "c" * 64,
        "sampling_sha256": "f" * 64,
        "timeout_ms": 30_000,
        "oracle_sha256": plan["oracle_sha256"],
        "case_sha256": {task["id"]: records[1]["case_sha256"] for task in plan["tasks"]},
        "input_token_limit": 100,
        "output_token_limit": 100,
        "budget_micro_usd": 1000,
    }
    rows = []
    for task in plan["tasks"]:
        for seed in plan["seeds"]:
            for arm in ["plain", "ddk"]:
                case, run, inputs, artifacts = copy.deepcopy(records)
                candidate = run["candidate_tree_sha256"]
                name = f"{task['id']}-{seed}-{arm}"
                report = {
                    "format": "ddk-benchmark-oracle/1",
                    "task_id": task["id"],
                    "seed": seed,
                    "arm": arm,
                    "candidate_tree_sha256": candidate,
                    "oracle_sha256": plan["oracle_sha256"],
                    "duration_ms": 1,
                    "executed_count": 3,
                    "failed_count": 0,
                    "skipped_count": 0,
                }
                report_path = tmp_path / (name + ".json")
                report_path.write_bytes(canonical_json(report))
                row = {
                    "task_id": task["id"],
                    "seed": seed,
                    "arm": arm,
                    "cohort_sha256": cohort_hash(cohort),
                    "upstream_commit": task["commit"],
                    "initial_tree_sha256": "e" * 64,
                    "candidate_tree_sha256": candidate,
                    "prompt_sha256": hashlib.sha256(task["request"].encode()).hexdigest(),
                    "agent_elapsed_ms": 100,
                    "cost_micro_usd": 1,
                    "model_calls": 1,
                    "claimed_ready": True,
                    "oracle_exit_code": 0,
                    "oracle_report": {
                        "path": report_path.name,
                        "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                    },
                    "host_record": {
                        "path": report_path.name,
                        "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
                    },
                    "gate_repository": None,
                    "run_id": None,
                    "run_sha256": None,
                }
                if arm == "ddk":
                    import uuid

                    run["run_id"] = str(uuid.uuid4())
                    store = VerifiedChangeStore(tmp_path / name)
                    store.publish_case(case, inputs)
                    store.begin_run(prepared_run(run))
                    store.publish_run(run, artifacts)
                    row.update(
                        gate_repository=name,
                        run_id=run["run_id"],
                        run_sha256=hashlib.sha256(store.run_bytes(run["run_id"])).hexdigest(),
                    )
                session_path = tmp_path / (name + "-session.txt")
                session_path.write_text("Fixture session only; no model invocation.")
                host = {
                    key: row[key]
                    for key in [
                        "task_id",
                        "seed",
                        "arm",
                        "cohort_sha256",
                        "upstream_commit",
                        "initial_tree_sha256",
                        "candidate_tree_sha256",
                        "prompt_sha256",
                        "agent_elapsed_ms",
                        "cost_micro_usd",
                        "model_calls",
                        "claimed_ready",
                    ]
                }
                host.update(
                    format="ddk-benchmark-host/1",
                    session_id=name,
                    cohort=cohort,
                    session_artifact={
                        "path": session_path.name,
                        "sha256": hashlib.sha256(session_path.read_bytes()).hexdigest(),
                    },
                )
                host_path = tmp_path / (name + "-host.json")
                host_path.write_bytes(canonical_json(host))
                row["host_record"] = {
                    "path": host_path.name,
                    "sha256": hashlib.sha256(host_path.read_bytes()).hexdigest(),
                }
                rows.append(row)
    value = {
        "format": "ddk-paired-receipts/1",
        "corpus_sha256": digest,
        "provenance": "fixture",
        "cohort": cohort,
        "rows": rows,
    }
    path = tmp_path / "receipts.json"
    path.write_text(json.dumps(value))
    return path, value


def check(path):
    return CliRunner().invoke(app, ["bench", "--receipts", str(path), "--json"])


def test_fixture_pairing_is_complete_but_never_measured_or_calibrated(receipts):
    path, _ = receipts
    result = check(path)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["status"] == "complete-fixture"
    assert data["calibrated"] is False and data["measured_records"] == 0
    assert data["arms"]["plain"]["oracle_passed"] == 9


@pytest.mark.parametrize(
    "mutation",
    ["missing", "duplicate", "cohort", "initial", "upstream", "prompt", "gate_hash", "path_escape"],
)
def test_incomparable_or_unbound_receipts_fail_closed(receipts, mutation):
    path, value = receipts
    if mutation == "missing":
        value["rows"].pop()
    elif mutation == "duplicate":
        value["rows"].append(value["rows"][0])
    elif mutation == "cohort":
        value["rows"][0]["cohort_sha256"] = "f" * 64
    elif mutation == "initial":
        value["rows"][0]["initial_tree_sha256"] = "f" * 64
    elif mutation == "upstream":
        value["rows"][0]["upstream_commit"] = "f" * 40
    elif mutation == "prompt":
        value["rows"][0]["prompt_sha256"] = "f" * 64
    elif mutation == "gate_hash":
        value["rows"][1]["run_sha256"] = "f" * 64
    else:
        value["rows"][0]["oracle_report"]["path"] = "../outside.json"
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code in (1, 5), result.output
    assert json.loads(result.stdout)["data"].get("calibrated") is not True


def test_green_report_cannot_override_nonzero_oracle_exit(receipts):
    path, value = receipts
    value["rows"][0]["oracle_exit_code"] = 7
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["arms"]["plain"]["oracle_failed"] == 1
    assert data["arms"]["plain"]["oracle_passed"] == 8


def test_unknown_costs_and_over_budget_attempts_are_retained(receipts):
    path, value = receipts
    row = value["rows"][0]
    row["cost_micro_usd"] = None
    host_path = path.parent / row["host_record"]["path"]
    host = json.loads(host_path.read_text())
    host["cost_micro_usd"] = None
    host_path.write_bytes(canonical_json(host))
    row["host_record"]["sha256"] = hashlib.sha256(host_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)["data"]
    assert data["arms"]["plain"]["cost_micro_usd"] is None
    assert data["recorded_records"] == 18


def test_a_provenance_label_cannot_promote_records_to_verified_measurements(receipts):
    path, value = receipts
    value["provenance"] = "measured"
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)["data"]
    assert data["declared_measured_records"] == 18
    assert data["measured_records"] == 0 and data["calibrated"] is False


def test_mutated_host_metadata_is_rejected_even_after_rehashing(receipts):
    path, value = receipts
    row = value["rows"][0]
    host_path = path.parent / row["host_record"]["path"]
    host = json.loads(host_path.read_text())
    host["cohort"]["model_revision"] = "different-model"
    host_path.write_bytes(canonical_json(host))
    row["host_record"]["sha256"] = hashlib.sha256(host_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code == 5


def test_zero_tests_are_preserved_as_an_incomplete_failed_observation(receipts):
    path, value = receipts
    row = value["rows"][0]
    report_path = path.parent / row["oracle_report"]["path"]
    report = json.loads(report_path.read_text())
    report["executed_count"] = 0
    report_path.write_bytes(canonical_json(report))
    row["oracle_report"]["sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(value))
    result = check(path)
    assert result.exit_code == 1, result.output
    data = json.loads(result.stdout)["data"]
    assert data["recorded_records"] == 18
    assert data["arms"]["plain"]["oracle_failed"] == 1


def test_corpus_pins_the_local_oracle_program():
    from ddk.services.paired_benchmark import corpus

    plan, _ = corpus()
    script = Path(__file__).resolve().parents[2] / "scripts/paired_benchmark.py"
    assert plan["oracle_sha256"] == hashlib.sha256(script.read_bytes()).hexdigest()

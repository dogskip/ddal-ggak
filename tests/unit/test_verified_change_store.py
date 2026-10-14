"""Exercise immutable manifests and real artifact integrity."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.verified_change_store import VerifiedChangeStore

EXAMPLES = json.loads(
    (
        Path(__file__).resolve().parents[2] / "docs/design/verified-change/contract-examples.json"
    ).read_text()
)


@pytest.fixture
def records():
    case = copy.deepcopy(EXAMPLES["valid"][0]["record"])
    run = copy.deepcopy(EXAMPLES["valid"][1]["record"])
    inputs = {}
    for index, item in enumerate(case["inputs"]):
        payload = f"input-{index}".encode()
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["size_bytes"] = len(payload)
        inputs[item["path"]] = payload
    for check in case["checks"]:
        check["definition_sha256"] = next(
            i["sha256"] for i in case["inputs"] if i["path"] == check["definition_path"]
        )
    artifacts = {}
    for index, item in enumerate(run["artifacts"]):
        payload = f"artifact-{index}".encode()
        item["sha256"] = hashlib.sha256(payload).hexdigest()
        item["size_bytes"] = len(payload)
        artifacts[item["path"]] = payload
    change = run["changes"][0]
    change["before_sha256"] = next(
        i["sha256"] for i in case["inputs"] if i["path"] == change["path"]
    )
    change["after_sha256"] = next(
        a["sha256"] for a in run["artifacts"] if a["artifact_id"] == change["after_artifact_id"]
    )
    run["case_sha256"] = record_digest(case)
    run["rounds"][0]["changes_sha256"] = record_digest(run["changes"])
    return case, run, inputs, artifacts


def prepared_run(run):
    pending = copy.deepcopy(run)
    pending.update(status="prepared", decision=None, finished_at=None, duration_ms=None)
    pending.update(results=[], artifacts=[], model_calls=[])
    pending["changes"] = []
    return pending


def test_case_and_completed_run_are_immutable_and_queryable(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    assert store.publish_case(case, inputs) == case
    assert store.publish_case(case, inputs) == case
    store.begin_run(prepared_run(run))
    assert store.publish_run(run, artifacts) == run
    assert store.case(case["case_id"]) == case
    assert store.run(run["run_id"]) == run
    assert record_digest(json.loads(store.run_bytes(run["run_id"]))) == record_digest(run)
    changed_case = copy.deepcopy(case)
    changed_case["request"] = "different request"
    with pytest.raises(ValueError, match="immutable"):
        store.publish_case(changed_case, inputs)
    changed_run = copy.deepcopy(run)
    changed_run["duration_ms"] += 1
    with pytest.raises(ValueError, match="immutable"):
        store.publish_run(changed_run, artifacts)


def test_pending_does_not_count_as_a_completed_run(tmp_path, records):
    case, run, inputs, _ = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    pending = prepared_run(run)
    assert store.begin_run(pending) == pending
    assert store.pending_run(run["run_id"]) == pending
    assert store.begin_run(pending) == pending
    with pytest.raises((ValueError, FileNotFoundError)):
        store.run(run["run_id"])
    conflicting = copy.deepcopy(pending)
    conflicting["request_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="request_conflict"):
        store.begin_run(conflicting)


@pytest.mark.parametrize("target", ["input", "artifact"])
def test_query_refuses_corrupted_real_files(tmp_path, records, target):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    if target == "input":
        path = store.path_for("case", case["case_id"]) / "inputs" / next(iter(inputs))
    else:
        path = store.path_for("run", run["run_id"]) / next(iter(artifacts))
    path.write_bytes(b"corruption")
    with pytest.raises((ValueError, OSError)):
        store.run(run["run_id"])


def test_symlink_storage_namespace_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / ".ddk").symlink_to(outside, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        VerifiedChangeStore(tmp_path)
    assert not list(outside.iterdir())


def test_missing_or_wrong_artifact_cannot_publish_manifest(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    broken = dict(artifacts)
    broken[next(iter(broken))] = b"bad"
    with pytest.raises(ValueError):
        store.publish_run(run, broken)
    assert not (store.path_for("run", run["run_id"]) / "run.json").exists()
    assert store.pending_run(run["run_id"])["status"] == "prepared"


def test_failed_artifact_write_never_publishes_completion(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    with (
        patch("ddk.services.verified_change_store.atomic_write", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        store.publish_run(run, artifacts)
    assert not (store.path_for("run", run["run_id"]) / "run.json").exists()


def test_orphan_partial_directory_never_restarts_request(tmp_path, records):
    case, run, inputs, _ = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.path_for("run", run["run_id"]).mkdir(mode=0o700)
    with pytest.raises(ValueError, match="incomplete_run"):
        store.begin_run(prepared_run(run))


def prepared_apply(store, run, inputs, artifacts):
    apply = copy.deepcopy(EXAMPLES["valid"][2]["record"])
    apply["run_sha256"] = record_digest(run)
    apply["changes_sha256"] = record_digest(run["changes"])
    for key in ("before_sha256", "after_sha256"):
        apply["entries"][0][key] = run["changes"][0][key]
    directory = store.path_for("apply", apply["apply_id"])
    for entry in apply["entries"]:
        for relative, payload in (
            (entry["backup_path"], inputs[entry["path"]]),
            (entry["staged_path"], artifacts["artifacts/new/App.tsx"]),
        ):
            target = directory / relative
            target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            from ddk.services.durable_files import atomic_write

            atomic_write(target, payload, exclusive=True)
    return apply


def test_apply_storage_uses_same_validated_contract(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    apply = prepared_apply(store, run, inputs, artifacts)
    assert store.publish_apply(apply) == apply
    assert store.load_apply(apply["apply_id"]) == apply
    conflict = copy.deepcopy(apply)
    conflict["entries"][0]["after_sha256"] = "e" * 64
    with pytest.raises(ValueError):
        store.publish_apply(conflict)


def test_missing_completed_artifact_is_rejected_without_repair(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    target = store.path_for("run", run["run_id"]) / next(iter(artifacts))
    target.unlink()
    with pytest.raises((ValueError, OSError)):
        store.publish_run(run, artifacts)
    assert not target.exists()
    with pytest.raises((ValueError, OSError)):
        store.begin_run(prepared_run(run))


def test_missing_fixed_input_is_rejected_without_repair(tmp_path, records):
    case, _, inputs, _ = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    target = store.path_for("case", case["case_id"]) / "inputs" / next(iter(inputs))
    target.unlink()
    with pytest.raises((ValueError, OSError)):
        store.publish_case(case, inputs)
    assert not target.exists()


def test_failed_directory_sync_does_not_publish_completion(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    original = __import__("os").fsync

    def fail_directory_sync(descriptor):
        import os
        import stat

        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("directory durability unavailable")
        return original(descriptor)

    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=fail_directory_sync),
        pytest.raises(OSError),
    ):
        store.publish_run(run, artifacts)
    assert not (store.path_for("run", run["run_id"]) / "run.json").exists()


def test_pending_reservations_cannot_be_removed(tmp_path, records):
    case, run, inputs, _ = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    pending = prepared_run(run)
    price = b"fixed price"
    pending["artifacts"] = [
        {
            "artifact_id": "price",
            "kind": "price",
            "path": "artifacts/price.json",
            "sha256": hashlib.sha256(price).hexdigest(),
            "size_bytes": len(price),
            "sensitive": False,
            "public_export_allowed": False,
        }
    ]
    pending["operation"] = "generation"
    pending["model_calls"] = [
        {
            "call_id": "00000000-0000-4000-8000-000000000008",
            "attempt_no": 1,
            "provider": "example",
            "model": "example",
            "price_artifact_id": "price",
            "state": "reserved",
            "reserved_micro_usd": 100,
            "calculated_micro_usd": None,
            "input_tokens": None,
            "output_tokens": None,
            "created_at": run["started_at"],
            "completed_at": None,
            "round_no": 0,
        }
    ]
    initial = copy.deepcopy(pending)
    initial["artifacts"] = []
    initial["model_calls"] = []
    store.begin_run(initial)
    directory = store.path_for("run", run["run_id"])
    (directory / "artifacts").mkdir(mode=0o700)
    (directory / "artifacts/price.json").write_bytes(price)
    (directory / "artifacts/price.json").chmod(0o600)
    store.save_pending(pending)
    erased = copy.deepcopy(pending)
    erased["model_calls"] = []
    with pytest.raises(ValueError, match="reservation_history"):
        store.save_pending(erased)


@pytest.mark.parametrize("relative", ["before/src/App.tsx", "staged/src/App.tsx"])
def test_apply_query_and_save_refuse_corrupted_saved_files(tmp_path, records, relative):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    apply = prepared_apply(store, run, inputs, artifacts)
    store.publish_apply(apply)
    target = store.path_for("apply", apply["apply_id"]) / relative
    target.write_bytes(b"foreign bytes")
    with pytest.raises((ValueError, OSError)):
        store.load_apply(apply["apply_id"])
    with pytest.raises((ValueError, OSError)):
        store.publish_apply(apply)
    assert target.read_bytes() == b"foreign bytes"


def test_apply_cannot_publish_before_all_saved_files_exist(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    apply = prepared_apply(store, run, inputs, artifacts)
    directory = store.path_for("apply", apply["apply_id"])
    (directory / apply["entries"][0]["staged_path"]).unlink()
    with pytest.raises((ValueError, OSError)):
        store.publish_apply(apply)
    assert not (directory / "apply.json").exists()


def apply_store(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    store.begin_run(prepared_run(run))
    store.publish_run(run, artifacts)
    return store, prepared_apply(store, run, inputs, artifacts)


@pytest.mark.parametrize("initial", [False, True])
def test_apply_rejects_state_shortcuts(tmp_path, records, initial):
    store, apply = apply_store(tmp_path, records)
    if not initial:
        store.publish_apply(apply)
    apply["state"] = "applied"
    apply["postcheck_at"] = apply["updated_at"]
    for entry in apply["entries"]:
        entry["state"] = "written"
    with pytest.raises(ValueError, match="apply_transition"):
        store.publish_apply(apply)


def test_conflict_is_terminal_and_the_saved_request_paths_are_fixed(tmp_path, records):
    store, apply = apply_store(tmp_path, records)
    store.publish_apply(apply)
    apply["state"] = "conflict"
    apply["entries"][0]["state"] = "conflict"
    store.publish_apply(apply)
    apply["state"] = "applying"
    with pytest.raises(ValueError, match="immutable_apply|apply_transition"):
        store.publish_apply(apply)


def test_new_case_keeps_an_existing_superseded_case(tmp_path, records):
    case, _, inputs, _ = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    following = copy.deepcopy(case)
    following["case_id"] = "00000000-0000-4000-8000-000000000099"
    following["supersedes_case_id"] = case["case_id"]
    assert store.publish_case(following, inputs) == following
    assert store.case(case["case_id"]) == case


def test_finished_check_result_cannot_disappear_from_pending_history(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    pending = prepared_run(run)
    store.begin_run(pending)
    directory = store.path_for("run", run["run_id"])
    from ddk.services.durable_files import atomic_write

    for path, payload in artifacts.items():
        target = directory / path
        target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        atomic_write(target, payload, exclusive=True)
    pending["artifacts"] = run["artifacts"]
    pending["results"] = [run["results"][0]]
    store.save_pending(pending)
    erased = copy.deepcopy(pending)
    erased["results"] = []
    with pytest.raises(ValueError, match="result_history"):
        store.save_pending(erased)


def test_stage_artifacts_validates_owned_pending_request_and_actual_files(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    pending = prepared_run(run)
    store.begin_run(pending)
    running = copy.deepcopy(run)
    running.update(status="running", decision=None, finished_at=None, duration_ms=None, results=[])
    store.stage_artifacts(running, artifacts)
    store.save_pending(running)
    assert store.pending_run(run["run_id"]) == running
    foreign = copy.deepcopy(running)
    foreign["request_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="request_conflict"):
        store.stage_artifacts(foreign, artifacts)
    with pytest.raises(ValueError, match="file_set_mismatch"):
        store.stage_artifacts(running, {})
    store.publish_run(run, artifacts)
    with pytest.raises(ValueError, match="immutable_run"):
        store.stage_artifacts(running, artifacts)


def test_claim_run_distinguishes_new_running_and_completed_requests(tmp_path, records):
    case, run, inputs, artifacts = records
    store = VerifiedChangeStore(tmp_path)
    store.publish_case(case, inputs)
    prepared = prepared_run(run)
    assert store.claim_run(prepared) == (prepared, True)
    assert store.claim_run(prepared) == (prepared, False)
    running = copy.deepcopy(prepared)
    running["status"] = "running"
    store.save_pending(running)
    assert store.claim_run(prepared) == (running, False)
    store.publish_run(run, artifacts)
    assert store.claim_run(prepared) == (run, False)
    foreign = copy.deepcopy(prepared)
    foreign["request_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="request_conflict"):
        store.claim_run(foreign)

from __future__ import annotations

import copy

import pytest

from ddk.models.verified_change import ContractError, validate_record
from ddk.services.verified_change_store import VerifiedChangeStore
from tests.unit.test_verified_change_engine import Evaluator, verify
from tests.unit.test_verified_change_engine import scenario as scenario


async def test_optional_context_records_validate_against_actual_artifacts(scenario):
    store, case, _, _ = scenario
    run = await verify(scenario, Evaluator())
    artifact = run["artifacts"][-1]
    context = {
        "round_no": 0,
        "source_artifact_id": artifact["artifact_id"],
        "compacted_artifact_id": artifact["artifact_id"],
        "compressor_kind": "raw",
        "raw_bytes": artifact["size_bytes"],
        "compacted_bytes": artifact["size_bytes"],
        "raw_sha256": artifact["sha256"],
        "compacted_sha256": artifact["sha256"],
    }
    extended = {**run, "context_digests": [context], "stall_diagnoses": [], "workspace_leases": []}
    validate_record(extended, {case["case_id"]: case}, {})
    for update in (
        {"raw_sha256": "0" * 64},
        {"raw_bytes": 999},
        {"round_no": 10},
        {"source_artifact_id": "missing"},
    ):
        invalid = copy.deepcopy(extended)
        invalid["context_digests"][0].update(update)
        with pytest.raises(ContractError):
            validate_record(invalid, {case["case_id"]: case}, {})
    with pytest.raises(ContractError):
        VerifiedChangeStore._retain_history(extended, run)


async def test_active_workspace_lease_prevents_ready_and_completed_receipt_is_immutable(scenario):
    _, case, _, _ = scenario
    run = await verify(scenario, Evaluator())
    lease = {
        "lease_id": "00000000-0000-4000-8000-000000000099",
        "round_no": 0,
        "phase": "candidate",
        "isolation_kind": "snapshot_copy",
        "base_tree_sha256": run["candidate_tree_sha256"],
        "state": "active",
        "acquired_at": run["started_at"],
        "released_at": None,
    }
    invalid = {**run, "workspace_leases": [lease]}
    with pytest.raises(ContractError):
        validate_record(invalid, {case["case_id"]: case}, {})
    lease.update(state="released", released_at=run["finished_at"])
    validate_record(invalid, {case["case_id"]: case}, {})
    changed = copy.deepcopy(invalid)
    changed["workspace_leases"][0]["state"] = "active"
    with pytest.raises(ContractError):
        VerifiedChangeStore._retain_history(invalid, changed)

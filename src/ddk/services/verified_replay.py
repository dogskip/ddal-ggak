"""Offline validation of sealed contracts and evidence; no execution or historical writes."""

from __future__ import annotations

from ddk.models.verified_change import Record, record_digest
from ddk.services.verified_budget import audit_run_costs
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_gate import expected_manifest


def replay_run(store: VerifiedChangeStore, run_id: str) -> Record:
    result: Record = {
        "run_id": run_id,
        "original_decision": None,
        "replay_decision": "blocked",
        "evidence_integrity": False,
        "execution_repeated": False,
        "read_only": True,
        "actions": [],
    }
    try:
        run = store.status(run_id)
        case = store.case(run["case_id"])
        result["original_decision"] = run["decision"]
        audit_run_costs(store, run)
        VerifiedChangeEngine(store).fixed_inputs(case)
        if run["candidate_tree_sha256"] is not None:
            expected_manifest(case, run)
        if store.status(run_id) != run or store.case(case["case_id"]) != case:
            raise ValueError("replay_evidence_changed")
        result.update(
            evidence_integrity=True, run_sha256=record_digest(run), case_sha256=record_digest(case)
        )
        if run["status"] == "completed" and run["decision"] in {
            "ready",
            "blocked",
            "manual-review",
        }:
            result["replay_decision"] = run["decision"]
        else:
            result["actions"] = [
                {"code": "replay_incomplete", "message": "The run has no completed verdict."}
            ]
    except (ValueError, OSError, KeyError, TypeError, AssertionError, StopIteration):
        result["actions"] = [
            {
                "code": "replay_evidence_invalid",
                "message": "The sealed contract or evidence failed validation.",
            }
        ]
    return result

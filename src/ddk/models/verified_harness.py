"""Relations for optional harness evidence in backward-compatible run records."""

from __future__ import annotations

from datetime import datetime

from ddk.models.verified_change import ContractError, Record


def harness_errors(record: Record, case: Record) -> list[str]:
    errors: list[str] = []
    artifacts = {a["artifact_id"]: a for a in record["artifacts"]}
    rounds = {r["round_no"]: r for r in record["rounds"]}
    observed = {a for r in record["results"] for a in r["artifact_ids"]}
    contexts = record.get("context_digests", [])
    keys = [(r["round_no"], r["source_artifact_id"]) for r in contexts]
    if len(keys) != len(set(keys)):
        errors.append("duplicate_context_digest")
    for item in contexts:
        source = artifacts.get(item["source_artifact_id"])
        compacted = artifacts.get(item["compacted_artifact_id"])
        if item["round_no"] not in rounds:
            errors.append("orphan_context_round")
        if item["source_artifact_id"] not in observed:
            errors.append("unobserved_context_source")
        for artifact, prefix in ((source, "raw"), (compacted, "compacted")):
            if (
                artifact is None
                or artifact["sha256"] != item[prefix + "_sha256"]
                or artifact["size_bytes"] != item[prefix + "_bytes"]
                or artifact["kind"] not in {"log", "trace", "data", "ax_snapshot"}
            ):
                errors.append("context_artifact_mismatch")
        if item["compacted_bytes"] > 65536:
            errors.append("context_size_limit")
    diagnoses = record.get("stall_diagnoses", [])
    keys = [r["round_no"] for r in diagnoses]
    if len(keys) != len(set(keys)):
        errors.append("duplicate_stall_diagnosis")
    for item in diagnoses:
        if item["round_no"] not in rounds or record["operation"] != "repair":
            errors.append("orphan_stall_round")
        if item["action_taken"] == "halt_repair_stalled" and (
            item["stall_category"] != "identical_error_signature"
            or item["streak_count"] < 3
            or record["decision"] == "ready"
        ):
            errors.append("invalid_stall_halt")
    leases = record.get("workspace_leases", [])
    keys = [r["lease_id"] for r in leases]
    if len(keys) != len(set(keys)):
        errors.append("duplicate_workspace_lease")
    for item in leases:
        round_record = rounds.get(item["round_no"])
        expected = (
            case["baseline_tree_sha256"]
            if item["phase"] == "baseline"
            else (round_record["candidate_tree_sha256"] if round_record else None)
        )
        if round_record is None or item["base_tree_sha256"] != expected:
            errors.append("workspace_tree_mismatch")
        if item["phase"] == "baseline" and item["round_no"] != 0:
            errors.append("workspace_baseline_round")
        if item["state"] == "released":
            if item["released_at"] is None or datetime.fromisoformat(
                item["released_at"]
            ) < datetime.fromisoformat(item["acquired_at"]):
                errors.append("workspace_release_time")
        elif item["released_at"] is not None:
            errors.append("workspace_unreleased_time")
        if record["decision"] in {"ready", "manual-review"} and item["state"] != "released":
            errors.append("workspace_cleanup_incomplete")
    return errors


def retain_harness_history(existing: Record, incoming: Record) -> None:
    for field, key_fields in (
        ("context_digests", ("round_no", "source_artifact_id")),
        ("stall_diagnoses", ("round_no",)),
        ("workspace_leases", ("lease_id",)),
    ):
        current = {tuple(row[k] for k in key_fields): row for row in incoming.get(field, [])}
        for old in existing.get(field, []):
            new = current.get(tuple(old[k] for k in key_fields))
            if new == old:
                continue
            if field != "workspace_leases" or new is None or old["state"] != "active":
                raise ContractError("harness_history_changed")
            if new["state"] not in {"released", "cleanup_failed"} or any(
                new[k] != old[k] for k in old if k not in {"state", "released_at"}
            ):
                raise ContractError("workspace_history_changed")

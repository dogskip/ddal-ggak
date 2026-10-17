"""Compare complete paired receipts without granting comparative product claims."""

from __future__ import annotations

import hashlib
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ddk.models.verified_change import MAX_RECORD_BYTES, Record, canonical_json, decode_json
from ddk.security.file_access import parent_descriptor, read_regular
from ddk.security.repo_paths import normalize_repo_relative_path, resolve_within_repository
from ddk.services.verified_change_store import VerifiedChangeStore

type Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
type Commit = Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
type Count = Annotated[int, Field(ge=0, le=2**53 - 1)]
type Label = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^\x00-\x1f\x7f]+$")]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Artifact(_Strict):
    path: str = Field(min_length=1, max_length=4096)
    sha256: Hash


class Cohort(_Strict):
    host: Label
    host_version: Label
    model: Label
    model_revision: Label
    ddk_commit: Commit
    environment_sha256: Hash
    sampling_sha256: Hash
    timeout_ms: Annotated[int, Field(ge=1, le=2**53 - 1)]
    permission_policy_sha256: Hash
    oracle_sha256: Hash
    case_sha256: dict[str, Hash]
    input_token_limit: Count
    output_token_limit: Count
    budget_micro_usd: Count


class _Episode(_Strict):
    task_id: Label
    seed: Count
    arm: Literal["plain", "ddk"]
    cohort_sha256: Hash
    upstream_commit: Commit
    initial_tree_sha256: Hash
    candidate_tree_sha256: Hash
    prompt_sha256: Hash
    agent_elapsed_ms: Count
    cost_micro_usd: Count | None
    model_calls: Count
    claimed_ready: bool


class Observation(_Episode):
    oracle_exit_code: int = Field(ge=-255, le=255)
    oracle_report: Artifact
    host_record: Artifact
    gate_repository: str | None
    run_id: str | None
    run_sha256: Hash | None


class HostRecord(_Episode):
    format: Literal["ddk-benchmark-host/1"]
    session_id: Label
    cohort: Cohort
    session_artifact: Artifact


class Receipts(_Strict):
    format: Literal["ddk-paired-receipts/1"]
    corpus_sha256: Hash
    provenance: Literal["fixture", "measured"]
    cohort: Cohort
    rows: list[Observation] = Field(max_length=10_000)


class OracleReport(_Strict):
    format: Literal["ddk-benchmark-oracle/1"]
    task_id: Label
    seed: Count
    arm: Literal["plain", "ddk"]
    candidate_tree_sha256: Hash
    oracle_sha256: Hash
    duration_ms: Count
    executed_count: Count
    failed_count: Count
    skipped_count: Count


def corpus() -> tuple[Record, str]:
    payload = files("ddk").joinpath("assets/benchmarks/paired-corpus.json").read_bytes()
    return decode_json(payload), hashlib.sha256(payload).hexdigest()


def cohort_hash(cohort: Record) -> str:
    return hashlib.sha256(canonical_json(cohort)).hexdigest()


def summarize_pairs(path: Path | None = None) -> Record:
    plan, digest = corpus()
    tasks = {task["id"]: task for task in plan["tasks"]}
    expected = {
        (task, seed, arm) for task in tasks for seed in plan["seeds"] for arm in ("plain", "ddk")
    }
    result: Record = {
        "format": "ddk-paired-summary/1",
        "status": "unmeasured",
        "calibrated": False,
        "corpus_sha256": digest,
        "repositories": len({t["repository"] for t in tasks.values()}),
        "expected_records": len(expected),
        "recorded_records": 0,
        "measured_records": 0,
        "arms": {},
        "problems": ["measurements_missing"],
    }
    if path is None:
        return result
    path = path.resolve()
    receipts = Receipts.model_validate(decode_json(read_regular(path, MAX_RECORD_BYTES)))
    if (
        receipts.corpus_sha256 != digest
        or set(receipts.cohort.case_sha256) != set(tasks)
        or receipts.cohort.oracle_sha256 != plan["oracle_sha256"]
    ):
        raise ValueError("comparison_corpus_mismatch")
    fixed = cohort_hash(receipts.cohort.model_dump())
    observed: dict[tuple[str, int, str], Observation] = {}
    totals: Record = {
        arm: {
            "records": 0,
            "oracle_passed": 0,
            "oracle_failed": 0,
            "gate_ready": 0,
            "ready_decisions": 0,
            "false_accepts": 0,
            "false_blocks": 0,
            "agent_elapsed_ms": 0,
            "oracle_elapsed_ms": 0,
            "cost_micro_usd": 0,
        }
        for arm in ("plain", "ddk")
    }
    problems: set[str] = set()
    referenced_runs: set[str] = set()
    sessions: set[str] = set()
    artifact_bytes = 0

    def artifact(reference: Artifact) -> bytes:
        nonlocal artifact_bytes
        payload = read_regular(
            resolve_within_repository(path.parent, reference.path), MAX_RECORD_BYTES
        )
        artifact_bytes += len(payload)
        if artifact_bytes > 64 * 1024**2 or hashlib.sha256(payload).hexdigest() != reference.sha256:
            raise ValueError("comparison_artifact_integrity")
        return payload

    for row in receipts.rows:
        key = (row.task_id, row.seed, row.arm)
        if key not in expected or key in observed:
            raise ValueError("comparison_matrix_invalid")
        task = tasks[row.task_id]
        if (
            row.cohort_sha256 != fixed
            or row.upstream_commit != task["commit"]
            or row.prompt_sha256 != hashlib.sha256(task["request"].encode()).hexdigest()
        ):
            raise ValueError("comparison_inputs_mismatch")
        observed[key] = row
        host = HostRecord.model_validate(decode_json(artifact(row.host_record)))
        episode = row.model_dump(include=set(_Episode.model_fields))
        if (
            host.model_dump(include=set(_Episode.model_fields)) != episode
            or cohort_hash(host.cohort.model_dump()) != fixed
            or host.session_id in sessions
        ):
            raise ValueError("comparison_host_mismatch")
        sessions.add(host.session_id)
        artifact(host.session_artifact)
        oracle = OracleReport.model_validate(decode_json(artifact(row.oracle_report)))
        if (
            oracle.task_id != row.task_id
            or oracle.seed != row.seed
            or oracle.arm != row.arm
            or oracle.candidate_tree_sha256 != row.candidate_tree_sha256
            or oracle.oracle_sha256 != receipts.cohort.oracle_sha256
            or oracle.failed_count > oracle.executed_count
        ):
            raise ValueError("comparison_oracle_mismatch")
        if oracle.executed_count == 0 or oracle.skipped_count:
            problems.add("oracle_incomplete")
        if receipts.provenance == "measured" and row.model_calls == 0:
            problems.add("model_observation_missing")
        if row.agent_elapsed_ms > receipts.cohort.timeout_ms:
            problems.add("time_limit_exceeded")
        if row.cost_micro_usd is None:
            problems.add("cost_unknown")
        elif row.cost_micro_usd > receipts.cohort.budget_micro_usd:
            problems.add("budget_exceeded")
        ready = False
        if row.arm == "ddk":
            if row.gate_repository is None or row.run_id is None or row.run_sha256 is None:
                raise ValueError("comparison_gate_missing")
            repository = path.parent / normalize_repo_relative_path(row.gate_repository)
            with parent_descriptor(repository / "record"):
                pass
            run_key = row.run_id
            if run_key in referenced_runs:
                raise ValueError("comparison_gate_reused")
            referenced_runs.add(run_key)
            store = VerifiedChangeStore(repository, create=False)
            run = store.run(row.run_id)
            if (
                hashlib.sha256(canonical_json(run)).hexdigest() != row.run_sha256
                or run["candidate_tree_sha256"] != row.candidate_tree_sha256
                or run["case_sha256"] != receipts.cohort.case_sha256[row.task_id]
            ):
                raise ValueError("comparison_gate_mismatch")
            ready = run["decision"] == "ready"
        elif any(value is not None for value in (row.gate_repository, row.run_id, row.run_sha256)):
            raise ValueError("comparison_plain_gate")
        passed = (
            row.oracle_exit_code == 0
            and oracle.executed_count > 0
            and not (oracle.failed_count or oracle.skipped_count)
        )
        summary = totals[row.arm]
        summary["records"] += 1
        summary["oracle_passed"] += int(passed)
        summary["oracle_failed"] += int(not passed)
        summary["gate_ready"] += int(ready)
        decision = ready if row.arm == "ddk" else row.claimed_ready
        summary["ready_decisions"] += int(decision)
        summary["false_accepts"] += int(decision and not passed)
        summary["false_blocks"] += int(not decision and passed)
        summary["agent_elapsed_ms"] += row.agent_elapsed_ms
        summary["oracle_elapsed_ms"] += oracle.duration_ms
        if row.cost_micro_usd is None or summary["cost_micro_usd"] is None:
            summary["cost_micro_usd"] = None
        else:
            summary["cost_micro_usd"] += row.cost_micro_usd
    if set(observed) != expected:
        problems.add("matrix_incomplete")
    for task in tasks:
        for seed in plan["seeds"]:
            pair = [observed.get((task, seed, arm)) for arm in ("plain", "ddk")]
            if (
                pair[0] is not None
                and pair[1] is not None
                and pair[0].initial_tree_sha256 != pair[1].initial_tree_sha256
            ):
                raise ValueError("comparison_initial_tree_mismatch")
    if any(
        isinstance(value, int) and value > 2**53 - 1
        for summary in totals.values()
        for value in summary.values()
    ):
        raise ValueError("comparison_sum_limit")
    result.update(
        status="incomplete"
        if problems
        else "complete-fixture"
        if receipts.provenance == "fixture"
        else "complete-records",
        recorded_records=len(observed),
        measured_records=0,
        declared_measured_records=len(observed) if receipts.provenance == "measured" else 0,
        measurement_review="not-reviewed",
        arms=totals,
        problems=sorted(problems),
    )
    return result

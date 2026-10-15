"""Model-free verification over explicit fixed inputs and an injected evaluator."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ddk.models.verified_change import ContractError, Record, record_digest, validate_record
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import (
    ensure_distinct_paths,
    normalize_change_path,
    normalize_source_path,
)
from ddk.services.source_snapshot import (
    SnapshotCancelledError,
    SnapshotError,
    SnapshotFile,
    SourceSnapshot,
    capture_git_source,
    capture_git_worktree,
    capture_source,
    manifest_digest,
    resolve_git_ref,
)
from ddk.services.verified_change_store import VerifiedChangeStore


@dataclass(frozen=True)
class EvaluationArtifact:
    artifact_id: str
    kind: str
    path: str
    content: bytes
    sensitive: bool = True
    public_export_allowed: bool = False

    def record(self) -> Record:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "path": self.path,
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "size_bytes": len(self.content),
            "sensitive": self.sensitive,
            "public_export_allowed": self.public_export_allowed,
        }


@dataclass(frozen=True)
class EvaluationRequest:
    case_id: str
    checks: tuple[Record, ...]
    phase: str
    snapshot: SourceSnapshot
    frozen_inputs: tuple[SnapshotFile, ...]
    environment_sha256: str
    evaluator_sha256: str
    input_tree_sha256: str
    deadline_ns: int
    cancelled: Callable[[], bool]
    limits: Mapping[str, int]
    baseline_snapshot: SourceSnapshot | None = None
    round_no: int = 0
    workspace_event: Callable[[Record], None] | None = None


@dataclass(frozen=True)
class EvaluationOutcome:
    results: tuple[Record, ...] = ()
    artifacts: tuple[EvaluationArtifact, ...] = ()
    assurance: str | None = None
    environment_sha256: str | None = None
    evaluator_sha256: str | None = None
    input_tree_sha256: str | None = None
    cleanup_complete: bool = False
    output_bytes: int | None = 0


class Evaluator(Protocol):
    async def evaluate(self, request: EvaluationRequest) -> EvaluationOutcome: ...


class VerificationStoppedError(ValueError):
    def __init__(self, code: str, target: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.target = target


def record_time() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _action(code: str, target: str = "") -> Record:
    messages = {
        "ambiguous_change_requirements": (
            "Provide change_requirements[path] with approved requirement IDs."
        ),
        "ambiguous_baseline": "Provide explicit baseline source and project_inputs mappings.",
    }
    return {
        "code": code,
        "target": target or "run",
        "message": messages.get(code, code),
        "retryable": code in {"snapshot_changed", "isolation_unavailable", "run_timeout"},
    }


class VerifiedChangeEngine:
    """Coordinate one owned verification request; never execute in an original directory."""

    def __init__(self, store: VerifiedChangeStore, evaluator: Evaluator | None = None) -> None:
        self.store = store
        self.evaluator = evaluator

    async def verify(
        self,
        case_id: str,
        *,
        baseline: Path | None,
        candidate: Path | None,
        run_id: str,
        project_inputs: Mapping[str, str] | None = None,
        change_requirements: Mapping[str, Sequence[str]] | None = None,
        cancelled: Callable[[], bool] | None = None,
        git_base: str | None = None,
        repository: Path | None = None,
    ) -> Record:
        started = time.monotonic_ns()
        case = self.store.case(case_id)
        deadline = started + case["limits"]["run_timeout_ms"] * 1_000_000
        git_repository = repository or self.store.repository
        if git_base is not None and baseline is not None:
            raise ValueError("git_base_conflicts_with_baseline")
        commit = resolve_git_ref(git_repository, git_base) if git_base is not None else None
        bindings = dict(project_inputs or {})
        links = {key: list(value) for key, value in (change_requirements or {}).items()}
        request: Record = {
            "case_sha256": record_digest(case),
            "operation": "verify",
            "baseline": "git:" + commit
            if commit
            else os.path.abspath(baseline)
            if baseline is not None
            else None,
            "candidate": os.path.abspath(candidate or git_repository)
            if commit
            else os.path.abspath(candidate)
            if candidate is not None
            else None,
            "project_inputs": bindings,
            "change_requirements": links,
            "assurance_required": case["assurance_required"],
        }
        baseline_snapshot: SourceSnapshot | None = None
        candidate_snapshot: SourceSnapshot | None = None
        frozen: tuple[SnapshotFile, ...] = ()
        changes: list[Record] = []
        artifacts: list[EvaluationArtifact] = []
        input_issue: VerificationStoppedError | None = None
        candidate_hash: str | None = None
        stop = cancelled or (lambda: False)

        def interrupted() -> bool:
            return stop() or time.monotonic_ns() >= deadline

        try:
            if commit is None and (baseline is None or candidate is None):
                raise VerificationStoppedError("ambiguous_baseline")
            frozen = self.fixed_inputs(case)
            file_limits = {
                "max_file_bytes": case["limits"]["max_file_bytes"],
                "max_total_bytes": case["limits"]["max_artifact_bytes"],
            }
            if commit is not None:
                baseline_snapshot = capture_git_source(git_repository, commit, **file_limits)
                candidate_snapshot = (
                    capture_source(candidate, **file_limits, cancelled=interrupted)
                    if candidate is not None
                    else capture_git_worktree(git_repository, **file_limits)
                )
            else:
                assert baseline is not None and candidate is not None
                baseline_snapshot = capture_source(baseline, **file_limits, cancelled=interrupted)
                candidate_snapshot = capture_source(candidate, **file_limits, cancelled=interrupted)
            candidate_hash, changes, artifacts = self._prepare(
                case, baseline_snapshot, candidate_snapshot, frozen, bindings, links
            )
        except SnapshotCancelledError:
            input_issue = VerificationStoppedError("cancelled" if stop() else "run_timeout")
        except SnapshotError as error:
            input_issue = VerificationStoppedError("snapshot_changed", str(error))
        except VerificationStoppedError as error:
            input_issue = error
        request.update(
            baseline_tree_sha256=baseline_snapshot.tree_sha256 if baseline_snapshot else None,
            candidate_tree_sha256=candidate_snapshot.tree_sha256 if candidate_snapshot else None,
        )
        prepared = self._prepared(case, run_id, record_digest(request), candidate_hash, changes)
        existing, claimed = self.store.claim_run(prepared)
        if not claimed:
            return existing
        record = copy.deepcopy(prepared)
        record["status"] = "running"
        record["changes"] = changes
        payloads: dict[str, bytes] = {}
        for artifact in artifacts:
            record["artifacts"].append(artifact.record())
            payloads[artifact.path] = artifact.content
        self._progress(record, payloads)
        if input_issue is not None:
            if input_issue.code == "cancelled":
                return self._cancel(record)
            return self._finish(record, case, started, payloads, input_issue)
        assert baseline_snapshot is not None and candidate_snapshot is not None
        remaining_output_bytes = case["limits"]["max_output_bytes"]
        try:
            for phase, snapshot, tree in [
                ("baseline", baseline_snapshot, case["baseline_tree_sha256"]),
                ("candidate", candidate_snapshot, candidate_hash),
            ]:
                if stop():
                    return self._cancel(record)
                if time.monotonic_ns() >= deadline:
                    raise VerificationStoppedError("run_timeout")
                if self.evaluator is None:
                    raise VerificationStoppedError("isolation_unavailable")
                assert tree is not None
                limits = copy.deepcopy(case["limits"])
                limits["max_output_bytes"] = remaining_output_bytes
                evaluation = EvaluationRequest(
                    case_id,
                    tuple(copy.deepcopy(case["checks"])),
                    phase,
                    snapshot,
                    frozen,
                    case["environment_sha256"],
                    case["evaluator_sha256"],
                    tree,
                    deadline,
                    interrupted,
                    limits,
                    baseline_snapshot,
                    workspace_event=self._workspace_observer(record, payloads),
                )
                record["integrity"]["cleanup_complete"] = False
                outcome = await self._evaluate(evaluation, case["limits"]["cleanup_timeout_ms"])
                self._merge(record, case, phase, outcome, payloads)
                self._progress(record, payloads)
                if (
                    type(outcome.output_bytes) is not int
                    or outcome.output_bytes < 0
                    or outcome.output_bytes > remaining_output_bytes
                ):
                    raise VerificationStoppedError("output_limit")
                remaining_output_bytes -= outcome.output_bytes
                self._phase_result(case, phase, outcome, tree)
                if self.store.case(case_id) != case:
                    raise VerificationStoppedError("criteria_changed")
            return self._finish(record, case, started, payloads)
        except asyncio.CancelledError:
            self._cancel(record)
            raise
        except VerificationStoppedError as error:
            return self._finish(record, case, started, payloads, error)

    def fixed_inputs(self, case: Record) -> tuple[SnapshotFile, ...]:
        files: list[SnapshotFile] = []
        for item in case["inputs"]:
            payload = read_regular(
                self.store.path_for("case", case["case_id"]) / "inputs" / item["path"],
                item["size_bytes"],
            )
            if (
                len(payload) != item["size_bytes"]
                or hashlib.sha256(payload).hexdigest() != item["sha256"]
            ):
                raise VerificationStoppedError(
                    "criteria_changed" if item["role"] == "criteria" else "protected_input_changed",
                    item["path"],
                )
            files.append(
                SnapshotFile(
                    item["path"], payload, item["sha256"], item["mode"], item["size_bytes"]
                )
            )
        for role, key, issue in [
            ("criteria", "evaluator_sha256", "criteria_changed"),
            ("environment", "environment_sha256", "environment_gap"),
        ]:
            selected = [
                file
                for file, item in zip(files, case["inputs"], strict=True)
                if item["role"] == role
            ]
            if not selected or manifest_digest(selected) != case[key]:
                raise VerificationStoppedError(issue)
        return tuple(
            file
            for file, item in zip(files, case["inputs"], strict=True)
            if item["role"] != "source"
        )

    @staticmethod
    def _prepare(
        case: Record,
        baseline: SourceSnapshot,
        candidate: SourceSnapshot,
        frozen: tuple[SnapshotFile, ...],
        bindings: Mapping[str, str],
        links: Mapping[str, Sequence[str]],
    ) -> tuple[str, list[Record], list[EvaluationArtifact]]:
        inputs = {item["path"]: item for item in case["inputs"]}
        source = {path: item for path, item in inputs.items() if item["role"] == "source"}
        fixed = {item.path: item for item in frozen}
        before = {item.path: item for item in baseline.files}
        after = {item.path: item for item in candidate.files}
        try:
            for path, input_path in bindings.items():
                normalize_source_path(path)
                if path in source or input_path not in fixed:
                    raise VerificationStoppedError("ambiguous_baseline", path)
            ensure_distinct_paths(list(source) + list(bindings))
        except ValueError as error:
            if isinstance(error, VerificationStoppedError):
                raise
            raise VerificationStoppedError("ambiguous_baseline", str(error)) from error
        expected = set(source) | set(bindings)
        if set(before) != expected:
            raise VerificationStoppedError(
                "ambiguous_baseline", ",".join(sorted(set(before) ^ expected))
            )
        for path, item in before.items():
            expected_input = inputs[bindings.get(path, path)]
            if any(
                getattr(item, key) != expected_input[key]
                for key in ["sha256", "mode", "size_bytes"]
            ):
                raise VerificationStoppedError("baseline_mismatch", path)
        if manifest_digest(before[path] for path in source) != case["baseline_tree_sha256"]:
            raise VerificationStoppedError("baseline_mismatch")
        for path, input_path in bindings.items():
            if path not in after or after[path].manifest_entry() != before[path].manifest_entry():
                role = inputs[input_path]["role"]
                raise VerificationStoppedError(
                    "criteria_changed" if role == "criteria" else "protected_input_changed", path
                )
        source_after = {path: item for path, item in after.items() if path not in bindings}
        requirements = {item["requirement_id"] for item in case["requirements"]}
        for path, requirement_ids in links.items():
            if (
                path not in set(source_after) | set(source)
                or path not in case["scope_paths"]
                or not requirement_ids
                or not set(requirement_ids) <= requirements
            ):
                raise VerificationStoppedError("invalid_change_requirements", path)
        changes: list[Record] = []
        artifacts: list[EvaluationArtifact] = []
        for path, item in source_after.items():
            previous = before.get(path)
            if previous is not None and previous.mode != item.mode:
                raise VerificationStoppedError("source_mode_changed", path)
            if previous is not None and previous.sha256 == item.sha256:
                continue
            if path not in case["scope_paths"]:
                raise VerificationStoppedError("outside_change_scope", path)
            try:
                normalize_change_path(path)
            except ValueError as error:
                raise VerificationStoppedError("protected_change", path) from error
            if previous is None and item.mode != 0o644:
                raise VerificationStoppedError("source_mode_changed", path)
            if path not in links:
                raise VerificationStoppedError("ambiguous_change_requirements", path)
            ident = f"source-{len(changes):04d}"
            artifacts.append(
                EvaluationArtifact(ident, "source", "artifacts/source/" + path, item.content)
            )
            changes.append(
                {
                    "path": path,
                    "action": "update" if previous else "create",
                    "before_sha256": previous.sha256 if previous else None,
                    "after_sha256": item.sha256,
                    "before_mode": previous.mode if previous else None,
                    "after_mode": item.mode,
                    "after_artifact_id": ident,
                    "requirement_ids": sorted(set(links[path])),
                }
            )
        for path in sorted(set(source) - set(source_after)):
            previous = before[path]
            ids = links.get(path, ())
            approved = [r for r in case["requirements"] if r["requirement_id"] in ids]
            if (
                path not in case["scope_paths"]
                or not ids
                or len(approved) != len(set(ids))
                or not all(
                    r.get("allow_delete", False)
                    and path in r.get("allowed_paths", case["scope_paths"])
                    for r in approved
                )
            ):
                raise VerificationStoppedError("source_delete_unsupported", path)
            normalize_change_path(path)
            changes.append(
                {
                    "path": path,
                    "action": "delete",
                    "before_sha256": previous.sha256,
                    "after_sha256": None,
                    "before_mode": previous.mode,
                    "after_mode": None,
                    "after_artifact_id": None,
                    "requirement_ids": sorted(set(ids)),
                }
            )
        if len(changes) > case["limits"]["max_changed_files"]:
            raise VerificationStoppedError("change_limit")
        return manifest_digest(source_after.values()), changes, artifacts

    @staticmethod
    def _prepared(
        case: Record,
        run_id: str,
        request_sha256: str,
        candidate_hash: str | None,
        changes: list[Record],
    ) -> Record:
        now = record_time()
        return {
            "record_type": "run",
            "schema_version": "verified-change/1",
            "run_id": run_id,
            "case_id": case["case_id"],
            "case_sha256": record_digest(case),
            "started_at": now,
            "finished_at": None,
            "status": "prepared",
            "decision": None,
            "assurance": None,
            "candidate_tree_sha256": candidate_hash,
            "environment_sha256": case["environment_sha256"],
            "evaluator_sha256": case["evaluator_sha256"],
            "integrity": dict.fromkeys(
                [
                    "case_match",
                    "criteria_match",
                    "environment_match",
                    "candidate_match",
                    "artifacts_complete",
                    "cleanup_complete",
                ],
                False,
            ),
            "results": [],
            "changes": [],
            "artifacts": [],
            "model_calls": [],
            "actions": [],
            "request_sha256": request_sha256,
            "operation": "verify",
            "source_run_id": None,
            "latest_round": 0 if candidate_hash else None,
            "rounds": [
                {
                    "round_no": 0,
                    "candidate_tree_sha256": candidate_hash,
                    "changes_sha256": record_digest(changes),
                    "started_at": now,
                    "finished_at": None,
                }
            ]
            if candidate_hash
            else [],
            "duration_ms": None,
        }

    def _progress(self, record: Record, payloads: Mapping[str, bytes]) -> None:
        self.store.stage_artifacts(record, payloads)
        self.store.save_pending(record)

    def _workspace_observer(
        self, record: Record, payloads: dict[str, bytes]
    ) -> Callable[[Record], None]:
        def changed(receipt: Record) -> None:
            leases = record.setdefault("workspace_leases", [])
            existing = next((r for r in leases if r["lease_id"] == receipt["lease_id"]), None)
            if existing is None:
                leases.append(receipt)
            else:
                existing.update(receipt)
            if receipt["state"] != "released":
                record["integrity"]["cleanup_complete"] = False
            self._progress(record, payloads)

        return changed

    async def _evaluate(self, request: EvaluationRequest, cleanup_ms: int) -> EvaluationOutcome:
        assert self.evaluator is not None
        task = asyncio.create_task(self.evaluator.evaluate(request))
        try:
            while not task.done():
                if request.cancelled():
                    raise VerificationStoppedError(
                        "run_timeout" if time.monotonic_ns() >= request.deadline_ns else "cancelled"
                    )
                remaining = (request.deadline_ns - time.monotonic_ns()) / 1_000_000_000
                if remaining <= 0:
                    raise VerificationStoppedError("run_timeout")
                await asyncio.wait({task}, timeout=min(0.02, remaining))
            outcome = task.result()
            return outcome
        except BaseException as error:
            task.cancel()
            done, _ = await asyncio.wait({task}, timeout=cleanup_ms / 1000)
            if task in done:
                if not task.cancelled():
                    task.exception()
            else:
                task.add_done_callback(
                    lambda finished: None if finished.cancelled() else finished.exception()
                )
            if isinstance(error, Exception) and not isinstance(error, VerificationStoppedError):
                raise VerificationStoppedError("evaluation_failed") from error
            raise

    @staticmethod
    def _merge(
        record: Record,
        case: Record,
        phase: str,
        outcome: EvaluationOutcome,
        payloads: dict[str, bytes],
        *,
        round_no: int = 0,
        source_runs: Record | None = None,
    ) -> None:
        candidate = copy.deepcopy(record)
        if any(
            result.get("phase") != phase or result.get("round_no") != round_no
            for result in outcome.results
        ):
            raise VerificationStoppedError("invalid_evaluation_result")
        candidate["results"].extend(copy.deepcopy(outcome.results))
        candidate["artifacts"].extend(artifact.record() for artifact in outcome.artifacts)
        if (
            sum(item["size_bytes"] for item in candidate["artifacts"])
            > case["limits"]["max_artifact_bytes"]
        ):
            raise VerificationStoppedError("artifact_limit")
        try:
            validate_record(candidate, {case["case_id"]: case}, source_runs or {})
        except ContractError as error:
            raise VerificationStoppedError("invalid_evaluation_result", str(error)) from error
        record.update(candidate)
        for artifact in outcome.artifacts:
            payloads[artifact.path] = artifact.content
        record["assurance"] = (
            outcome.assurance if outcome.assurance in {"isolated", "trusted-local"} else None
        )
        record["integrity"].update(
            case_match=True,
            criteria_match=outcome.evaluator_sha256 == case["evaluator_sha256"],
            environment_match=outcome.environment_sha256 == case["environment_sha256"],
            candidate_match=outcome.input_tree_sha256
            == (
                case["baseline_tree_sha256"]
                if phase == "baseline"
                else record["candidate_tree_sha256"]
            ),
            artifacts_complete=True,
            cleanup_complete=outcome.cleanup_complete,
        )

    @staticmethod
    def _phase_result(
        case: Record, phase: str, outcome: EvaluationOutcome, expected_tree: str
    ) -> None:
        if outcome.input_tree_sha256 != expected_tree:
            raise VerificationStoppedError("candidate_mismatch")
        if not outcome.cleanup_complete:
            raise VerificationStoppedError("cleanup_failed")
        if outcome.environment_sha256 != case["environment_sha256"]:
            raise VerificationStoppedError("environment_gap")
        if outcome.evaluator_sha256 != case["evaluator_sha256"]:
            raise VerificationStoppedError("criteria_changed")
        if outcome.assurance not in {"isolated", "trusted-local"} or (
            case["assurance_required"] == "isolated" and outcome.assurance != "isolated"
        ):
            raise VerificationStoppedError("isolation_unavailable")
        mapped = {result["check_id"]: result for result in outcome.results}
        for check in case["checks"]:
            if not check["required"]:
                continue
            result = mapped.get(check["check_id"])
            acceptable = (
                {"passed", "failed"}
                if phase == "baseline" and check["role"] == "target"
                else {"passed"}
            )
            if result is not None:
                invalid_observation = check["kind"] in {"browser", "visual", "policy"} and (
                    result["evidence_origin"] != "trusted-observer" or not result["artifact_ids"]
                )
                invalid_test = check["kind"] == "test" and (
                    (result["executed_count"] or 0) == 0
                    or (result["skipped_count"] != 0 and not check.get("allow_skipped", False))
                    or (result["status"] == "passed" and result["failed_count"] != 0)
                )
                invalid_command = check["kind"] in {"command", "test"} and (
                    result["status"] == "passed" and result["exit_code"] != 0
                )
                if invalid_observation or invalid_test or invalid_command:
                    raise VerificationStoppedError(
                        "baseline_failed"
                        if phase == "baseline"
                        else "required_evidence_incomplete",
                        check["check_id"],
                    )
            if result is None or result["status"] not in acceptable:
                raise VerificationStoppedError(
                    "baseline_failed" if phase == "baseline" else "required_check_failed",
                    check["check_id"],
                )

    def _finish(
        self,
        record: Record,
        case: Record,
        started: int,
        payloads: Mapping[str, bytes],
        issue: VerificationStoppedError | None = None,
        *,
        source_runs: Record | None = None,
    ) -> Record:
        if issue is not None and issue.code == "cancelled":
            return self._cancel(record)
        record["status"] = "completed"
        record["finished_at"] = record_time()
        record["duration_ms"] = (time.monotonic_ns() - started) // 1_000_000
        record["decision"] = "blocked" if issue else "ready"
        latest = record["latest_round"]
        for item in record["rounds"]:
            if item["round_no"] == latest and item["finished_at"] is None:
                item["finished_at"] = record["finished_at"]
        if issue:
            record["actions"].append(_action(issue.code, issue.target))
            if issue.code == "cleanup_failed":
                record["integrity"]["cleanup_complete"] = False
        if not issue:
            mapped = {
                item["check_id"]: item
                for item in record["results"]
                if item["phase"] == "candidate" and item["round_no"] == latest
            }
            for check in case["checks"]:
                if (
                    not check["required"]
                    and mapped.get(check["check_id"], {}).get("status") != "passed"
                ):
                    record["decision"] = "manual-review"
                    record["actions"].append(_action("advisory_check_failed", check["check_id"]))
        if not issue:
            try:
                validate_record(record, {case["case_id"]: case}, source_runs or {})
            except ContractError as error:
                record["decision"] = "blocked"
                record["actions"].append(_action("required_evidence_incomplete", str(error)))
        return self.store.publish_run(record, payloads)

    def _cancel(self, record: Record) -> Record:
        record["status"] = "cancelled"
        record["decision"] = None
        record["finished_at"] = record_time()
        record["integrity"]["cleanup_complete"] = False
        record["actions"].append(_action("cancelled"))
        self.store.save_pending(record)
        return record

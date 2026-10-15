"""Validated immutable records in the verified-change file namespace."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

from ddk.models.verified_change import (
    MAX_RECORD_BYTES,
    ContractError,
    Record,
    application_changes,
    canonical_json,
    decode_json,
    safe_path,
    validate_record,
    validate_structure,
)
from ddk.security.file_access import parent_descriptor
from ddk.security.repo_paths import ensure_distinct_paths
from ddk.services.durable_files import atomic_write, ensure_directory, read_regular
from ddk.services.source_snapshot import SnapshotFile

_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
_DIRECTORIES = {"case": "cases", "run": "runs", "apply": "applies"}
_REQUEST_KEYS = ("run_id", "case_id", "case_sha256", "request_sha256", "operation", "source_run_id")
_APPLY_KEYS = (
    "apply_id",
    "case_id",
    "run_id",
    "run_sha256",
    "changes_sha256",
    "created_at",
    "quiescence_confirmed_at",
)

_APPLY_TRANSITIONS: dict[str, set[str]] = {
    "prepared": {"applying", "conflict"},
    "applying": {"applied", "rolling_back", "unknown"},
    "rolling_back": {"rolled_back", "unknown"},
    "applied": set(),
    "rolled_back": set(),
    "conflict": set(),
    "unknown": set(),
}


class VerifiedChangeStore:
    """Publish referenced files first and their validated manifest last."""

    def __init__(self, repository: Path, *, create: bool = True) -> None:
        self.repository = Path(os.path.abspath(repository))
        self.base_path = self.repository / ".ddk/verified-change/1"
        if create:
            self.initialize()

    def initialize(self) -> None:
        """Prepare owned storage only for an explicit writing operation."""
        for suffix in ("cases", "runs", "applies", "locks/model"):
            ensure_directory(self.base_path / suffix)

    def path_for(self, kind: str, identifier: str) -> Path:
        if kind not in _DIRECTORIES or _ID.fullmatch(identifier) is None:
            raise ContractError("invalid_record_identifier")
        return self.base_path / _DIRECTORIES[kind] / identifier

    def _metadata(self, path: Path) -> tuple[Record, bytes]:
        payload = read_regular(path, MAX_RECORD_BYTES)
        record = decode_json(payload)
        if canonical_json(record) != payload:
            raise ContractError("noncanonical_stored_record")
        return record, payload

    @staticmethod
    def _manifest_exists(path: Path) -> bool:
        try:
            with parent_descriptor(path) as (parent_fd, name):
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            return False
        return True

    def _case(self, case_id: str, visited: frozenset[str] = frozenset()) -> Record:
        if case_id in visited:
            raise ContractError("superseded_case_cycle")
        record, _ = self._metadata(self.path_for("case", case_id) / "case.json")
        if record.get("record_type") != "case" or record.get("case_id") != case_id:
            raise ContractError("case_identity_mismatch")
        validate_structure(record)
        contexts: Record = {}
        previous = record["supersedes_case_id"]
        if previous is not None:
            contexts[previous] = self._case(previous, visited | {case_id})
        validate_record(record, contexts)
        self._verify_files(
            self.path_for("case", case_id) / "inputs",
            record["inputs"],
            record["limits"]["max_file_bytes"],
        )
        return record

    def case(self, case_id: str) -> Record:
        return self._case(case_id)

    def case_bytes(self, case_id: str) -> bytes:
        record = self.case(case_id)
        return canonical_json(record)

    def _contexts(
        self, record: Record, visited: frozenset[str] = frozenset()
    ) -> tuple[Record, Record]:
        if len(visited) >= 32:
            raise ContractError("source_run_depth")
        case = self.case(record["case_id"])
        cases = {case["case_id"]: case}
        runs: Record = {}
        source_id = record.get("source_run_id")
        if source_id is not None:
            if source_id == record["run_id"] or source_id in visited:
                raise ContractError("source_run_cycle")
            source = self._run(source_id, visited | {record["run_id"]})
            runs[source_id] = source
        return cases, runs

    def _validate_run(self, record: Record, visited: frozenset[str] = frozenset()) -> Record:
        validate_structure(record)
        if record["record_type"] != "run":
            raise ContractError("run_record_required")
        cases, runs = self._contexts(record, visited)
        validate_record(record, cases, runs)
        return dict(cases[record["case_id"]])

    def _run(self, run_id: str, visited: frozenset[str] = frozenset()) -> Record:
        record, _ = self._metadata(self.path_for("run", run_id) / "run.json")
        if record.get("record_type") != "run" or record.get("run_id") != run_id:
            raise ContractError("run_identity_mismatch")
        case = self._validate_run(record, visited)
        if record["status"] != "completed":
            raise ContractError("incomplete_run")
        self._verify_artifacts(record, case)
        return record

    def run(self, run_id: str) -> Record:
        return self._run(run_id)

    def run_bytes(self, run_id: str) -> bytes:
        return canonical_json(self.run(run_id))

    def pending_run(self, run_id: str) -> Record:
        record, _ = self._metadata(self.path_for("run", run_id) / ".pending/run.json")
        if record.get("record_type") != "run" or record.get("run_id") != run_id:
            raise ContractError("run_identity_mismatch")
        case = self._validate_run(record)
        if record["status"] == "completed":
            raise ContractError("completed_pending_record")
        self._verify_artifacts(record, case)
        return record

    def _existing_run(self, run_id: str) -> Record:
        if self._manifest_exists(self.path_for("run", run_id) / "run.json"):
            return self.run(run_id)
        return self.pending_run(run_id)

    def status(self, run_id: str) -> Record:
        """Validate the published or pending record without resuming execution."""
        return self._existing_run(run_id)

    def publish_case(self, record: Record, inputs: Mapping[str, bytes]) -> Record:
        validate_structure(record)
        if record["record_type"] != "case":
            raise ContractError("case_record_required")
        previous = record["supersedes_case_id"]
        if previous == record["case_id"]:
            raise ContractError("superseded_case_missing_or_self")
        contexts = {previous: self.case(previous)} if previous is not None else {}
        validate_record(record, contexts)
        case_id = record["case_id"]
        directory = self.path_for("case", case_id)
        existing = self.case(case_id) if self._manifest_exists(directory / "case.json") else None
        if existing is not None:
            if canonical_json(existing) != canonical_json(record):
                raise ContractError("immutable_case")
            return existing
        ensure_directory(directory / "inputs")
        self._publish_files(
            directory / "inputs", record["inputs"], inputs, record["limits"]["max_file_bytes"]
        )
        atomic_write(directory / "case.json", canonical_json(record), exclusive=True)
        from ddk.services.verified_index import sync_index

        sync_index(self, "upsert_case", record)
        return self.case(case_id)

    @staticmethod
    def _same_request(existing: Record, incoming: Record) -> None:
        if any(existing.get(key) != incoming.get(key) for key in _REQUEST_KEYS):
            raise ContractError("request_conflict")

    def begin_run(self, record: Record) -> Record:
        return self.claim_run(record)[0]

    def claim_run(self, record: Record) -> tuple[Record, bool]:
        self._validate_run(record)
        if record["status"] != "prepared":
            raise ContractError("prepared_run_required")
        directory = self.path_for("run", record["run_id"])
        with parent_descriptor(directory) as (parent_fd, name):
            try:
                os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            except FileExistsError:
                try:
                    existing = self._existing_run(record["run_id"])
                except FileNotFoundError as error:
                    raise ContractError("incomplete_run") from error
                self._same_request(existing, record)
                return existing, False
            os.fsync(parent_fd)
        ensure_directory(directory / ".pending")
        atomic_write(directory / ".pending/run.json", canonical_json(record), exclusive=True)
        from ddk.services.verified_index import sync_index

        sync_index(self, "upsert_run", record)
        return self.pending_run(record["run_id"]), True

    @staticmethod
    def _retain_history(existing: Record, incoming: Record) -> None:
        calls = {item["call_id"]: item for item in incoming["model_calls"]}
        immutable = (
            "call_id",
            "attempt_no",
            "provider",
            "model",
            "price_artifact_id",
            "reserved_micro_usd",
            "created_at",
            "round_no",
            "cache_prefix_sha256",
        )
        for previous in existing["model_calls"]:
            current = calls.get(previous["call_id"])
            if current is None or any(current.get(key) != previous.get(key) for key in immutable):
                raise ContractError("reservation_history_changed")
            if previous["state"] in {"settled", "unknown"} and current != previous:
                raise ContractError("reservation_history_changed")
        rounds = {item["round_no"]: item for item in incoming["rounds"]}
        for previous in existing["rounds"]:
            current = rounds.get(previous["round_no"])
            if current is None or (previous["finished_at"] is not None and current != previous):
                raise ContractError("round_history_changed")
        results = {
            (item["round_no"], item["phase"], item["check_id"]): item
            for item in incoming["results"]
        }
        if any(
            results.get((item["round_no"], item["phase"], item["check_id"])) != item
            for item in existing["results"]
        ):
            raise ContractError("result_history_changed")
        artifacts = {item["artifact_id"]: item for item in incoming["artifacts"]}
        if any(artifacts.get(item["artifact_id"]) != item for item in existing["artifacts"]):
            raise ContractError("artifact_history_changed")
        from ddk.models.verified_harness import retain_harness_history

        retain_harness_history(existing, incoming)

    def save_pending(self, record: Record) -> None:
        case = self._validate_run(record)
        if record["status"] == "completed":
            raise ContractError("completed_pending_record")
        existing = self._existing_run(record["run_id"])
        self._same_request(existing, record)
        self._retain_history(existing, record)
        if existing["status"] == "completed":
            raise ContractError("immutable_run")
        if existing["status"] in {"cancelled", "failed"}:
            raise ContractError("terminal_run")
        if existing["status"] == "running" and record["status"] == "prepared":
            raise ContractError("run_transition")
        self._verify_artifacts(record, case)
        atomic_write(
            self.path_for("run", record["run_id"]) / ".pending/run.json", canonical_json(record)
        )
        from ddk.services.verified_index import sync_index

        sync_index(self, "upsert_run", record)

    def stage_artifacts(self, record: Record, payloads: Mapping[str, bytes]) -> None:
        case = self._validate_run(record)
        directory = self.path_for("run", record["run_id"])
        if self._manifest_exists(directory / "run.json"):
            raise ContractError("immutable_run")
        existing = self.pending_run(record["run_id"])
        self._same_request(existing, record)
        self._retain_history(existing, record)
        if existing["status"] in {"cancelled", "failed"}:
            raise ContractError("terminal_run")
        self._artifact_paths(record)
        if (
            sum(item["size_bytes"] for item in record["artifacts"])
            > case["limits"]["max_artifact_bytes"]
        ):
            raise ContractError("artifact_limit")
        self._publish_files(
            directory, record["artifacts"], payloads, case["limits"]["max_artifact_bytes"]
        )
        self._verify_artifacts(record, case)

    def publish_run(self, record: Record, artifacts: Mapping[str, bytes]) -> Record:
        case = self._validate_run(record)
        if record["status"] != "completed":
            raise ContractError("completed_run_required")
        directory = self.path_for("run", record["run_id"])
        completed = (
            self.run(record["run_id"]) if self._manifest_exists(directory / "run.json") else None
        )
        if completed is not None:
            self._same_request(completed, record)
            if canonical_json(completed) != canonical_json(record):
                raise ContractError("immutable_run")
            return completed
        pending = self.pending_run(record["run_id"])
        self._same_request(pending, record)
        self._retain_history(pending, record)
        if pending["status"] in {"cancelled", "failed"}:
            raise ContractError("terminal_run")
        self._artifact_paths(record)
        self._publish_files(
            directory, record["artifacts"], artifacts, case["limits"]["max_artifact_bytes"]
        )
        self._verify_artifacts(record, case)
        atomic_write(directory / "run.json", canonical_json(record), exclusive=True)
        from ddk.services.verified_index import sync_index

        sync_index(self, "upsert_run", record)
        return self.run(record["run_id"])

    @staticmethod
    def _artifact_paths(record: Record) -> None:
        if any(not item["path"].startswith("artifacts/") for item in record["artifacts"]):
            raise ContractError("artifact_namespace_required")

    def _verify_artifacts(self, record: Record, case: Record) -> None:
        self._artifact_paths(record)
        self._verify_files(
            self.path_for("run", record["run_id"]),
            record["artifacts"],
            case["limits"]["max_artifact_bytes"],
        )

    @staticmethod
    def _verify_files(directory: Path, items: list[Record], max_bytes: int) -> None:
        for item in items:
            if not safe_path(item["path"]):
                raise ContractError("unsafe_stored_path")
            payload = read_regular(directory / item["path"], min(max_bytes, item["size_bytes"]))
            if (
                len(payload) != item["size_bytes"]
                or hashlib.sha256(payload).hexdigest() != item["sha256"]
            ):
                raise ContractError("stored_file_integrity")
            if stat.S_IMODE((directory / item["path"]).lstat().st_mode) != 0o600:
                raise ContractError("stored_file_mode")

    @classmethod
    def _publish_files(
        cls, directory: Path, items: list[Record], payloads: Mapping[str, bytes], max_bytes: int
    ) -> None:
        if set(payloads) != {item["path"] for item in items}:
            raise ContractError("file_set_mismatch")
        for item in items:
            payload = payloads[item["path"]]
            if (
                not safe_path(item["path"])
                or len(payload) != item["size_bytes"]
                or len(payload) > max_bytes
                or hashlib.sha256(payload).hexdigest() != item["sha256"]
            ):
                raise ContractError("file_payload_integrity")
        for item in items:
            path = directory / item["path"]
            ensure_directory(path.parent)
            try:
                existing = read_regular(path, max_bytes)
            except FileNotFoundError:
                atomic_write(path, payloads[item["path"]], exclusive=True)
            else:
                if existing != payloads[item["path"]]:
                    raise ContractError("immutable_stored_file")
        cls._verify_files(directory, items, max_bytes)

    def application_sources(
        self, run: Record, target_run_id: str | None = None, *, final: bool = False
    ) -> dict[str, SnapshotFile | None]:
        case = self.case(run["case_id"])
        if target_run_id is not None and target_run_id not in {run["run_id"], run["source_run_id"]}:
            raise ContractError("application_source_not_bound")
        target = self.run(target_run_id) if target_run_id is not None else None
        if target is not None and target["case_id"] != run["case_id"]:
            raise ContractError("application_source_case_mismatch")
        plan = application_changes(case, run, target)
        if final:
            target = run
        baseline = {i["path"]: i for i in case["inputs"] if i["role"] == "source"}
        changes = {c["path"]: c for c in target["changes"]} if target is not None else {}
        artifacts = {a["artifact_id"]: a for a in target["artifacts"]} if target is not None else {}
        answer: dict[str, SnapshotFile | None] = {}
        for change in plan:
            path = change["path"]
            if path in changes:
                row = changes[path]
                if row["after_sha256"] is None:
                    answer[path] = None
                    continue
                artifact = artifacts[row["after_artifact_id"]]
                assert target is not None
                content = read_regular(
                    self.path_for("run", target["run_id"]) / artifact["path"],
                    artifact["size_bytes"],
                )
                answer[path] = SnapshotFile(
                    path, content, row["after_sha256"], row["after_mode"], len(content)
                )
            elif path in baseline:
                row = baseline[path]
                content = read_regular(
                    self.path_for("case", case["case_id"]) / "inputs" / path, row["size_bytes"]
                )
                answer[path] = SnapshotFile(path, content, row["sha256"], row["mode"], len(content))
            else:
                answer[path] = None
        return answer

    def _validate_apply(self, record: Record) -> None:
        validate_structure(record)
        if record["record_type"] != "apply":
            raise ContractError("apply_record_required")
        run = self.run(record["run_id"])
        case = self.case(record["case_id"])
        contexts = {run["run_id"]: run}
        if record.get("target_run_id") is not None:
            contexts[record["target_run_id"]] = self.run(record["target_run_id"])
        validate_record(record, {case["case_id"]: case}, contexts)
        directory = self.path_for("apply", record["apply_id"])
        sources = self.application_sources(run, record.get("target_run_id"))
        finals = self.application_sources(run, record.get("target_run_id"), final=True)
        saved: list[Record] = []
        for entry in record["entries"]:
            if entry["after_sha256"] is None:
                if entry["staged_path"] is not None:
                    raise ContractError("delete_staged_not_null")
            else:
                staged = finals[entry["path"]]
                if staged is None:
                    raise ContractError("staged_source_missing")
                if not entry["staged_path"].startswith("staged/"):
                    raise ContractError("staged_namespace_required")
                saved.append(
                    {
                        "path": entry["staged_path"],
                        "sha256": entry["after_sha256"],
                        "size_bytes": staged.size_bytes,
                    }
                )
            if entry["before_sha256"] is None:
                if entry["backup_path"] is not None:
                    raise ContractError("unexpected_create_backup")
            else:
                if not entry["backup_path"].startswith("before/"):
                    raise ContractError("backup_namespace_required")
                source = sources[entry["path"]]
                if source is None:
                    raise ContractError("backup_source_missing")
                saved.append(
                    {
                        "path": entry["backup_path"],
                        "sha256": entry["before_sha256"],
                        "size_bytes": source.size_bytes,
                    }
                )
        ensure_distinct_paths([item["path"] for item in saved])
        self._verify_files(directory, saved, case["limits"]["max_file_bytes"])

    def publish_apply(self, record: Record) -> Record:
        self._validate_apply(record)
        directory = self.path_for("apply", record["apply_id"])
        existing = (
            self.load_apply(record["apply_id"])
            if self._manifest_exists(directory / "apply.json")
            else None
        )
        if existing is not None:
            if any(existing[key] != record[key] for key in _APPLY_KEYS) or existing.get(
                "target_run_id"
            ) != record.get("target_run_id"):
                raise ContractError("request_conflict")
            old_entries = {
                entry["path"]: {k: v for k, v in entry.items() if k != "state"}
                for entry in existing["entries"]
            }
            new_entries = {
                entry["path"]: {k: v for k, v in entry.items() if k != "state"}
                for entry in record["entries"]
            }
            if existing.get("target_run_id") != record.get("target_run_id"):
                raise ContractError("request_conflict")
            if old_entries != new_entries:
                raise ContractError("request_conflict")
            if not _APPLY_TRANSITIONS[existing["state"]]:
                if canonical_json(existing) != canonical_json(record):
                    raise ContractError("immutable_apply")
                return existing
            if (
                record["state"] != existing["state"]
                and record["state"] not in _APPLY_TRANSITIONS[existing["state"]]
            ):
                raise ContractError("apply_transition")
        elif record["state"] != "prepared":
            raise ContractError("apply_transition")
        ensure_directory(directory)
        atomic_write(directory / "apply.json", canonical_json(record), exclusive=existing is None)
        from ddk.services.verified_index import sync_index

        sync_index(self, "upsert_transaction", record)
        return self.load_apply(record["apply_id"])

    def load_apply(self, apply_id: str) -> Record:
        record, _ = self._metadata(self.path_for("apply", apply_id) / "apply.json")
        if record.get("record_type") != "apply" or record.get("apply_id") != apply_id:
            raise ContractError("apply_identity_mismatch")
        self._validate_apply(record)
        return record

"""ArtifactApplier — copy the files of a finished case into the repository, safely.

A file is written only when the repository still holds the version the run started from
(or nothing yet); anything edited since is reported as a conflict, and a replaced file is
kept in a backup folder.
"""

from __future__ import annotations

import hashlib
import os
import stat
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.verified_change import Record, parse_record, record_digest
from ddk.security.file_access import file_identity, parent_descriptor, read_regular
from ddk.security.repo_paths import (
    ensure_distinct_paths,
    resolve_change_path,
    resolve_within_repository,
)
from ddk.services.durable_files import OwnedLock, atomic_write, ensure_directory, sync_directory
from ddk.services.verified_change_store import VerifiedChangeStore

Action = Literal["create", "update", "unchanged", "conflict", "rejected"]


@dataclass(frozen=True)
class FileChange:
    """What applying one generated file would do."""

    path: str
    action: Action
    content: str
    reason: str = ""
    before_sha256: str | None = None
    before_mode: int | None = None


@dataclass(frozen=True)
class _FileState:
    content: bytes
    mode: int
    identity: tuple[int, ...] = field(default=(), compare=False)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()


def _state(path: Path) -> _FileState | None:
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    try:
        content = read_regular(path, 2 * 1024 * 1024)
        after = path.lstat()
    except FileNotFoundError as error:
        raise ValueError("file_state_changed") from error
    if file_identity(before) != file_identity(after):
        raise ValueError("file_state_changed")
    return _FileState(content, stat.S_IMODE(after.st_mode), file_identity(after))


def _matches(state: _FileState | None, sha256: str | None, mode: int | None) -> bool:
    if state is None:
        return sha256 is None and mode is None
    return state.sha256 == sha256 and state.mode == mode


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _confirm_restored(path: Path, expected: _FileState | None, repository: Path) -> None:
    current = _state(path)
    if current != expected:
        raise ValueError("restored_state_changed")
    if current is None:
        parent = path.parent
        while True:
            try:
                parent.lstat()
            except FileNotFoundError:
                if parent == repository or parent == parent.parent:
                    raise ValueError("restored_parent_missing") from None
                parent = parent.parent
            else:
                sync_directory(parent)
                break
    else:
        with parent_descriptor(path) as (parent_fd, name):
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
            )
            try:
                if file_identity(os.fstat(descriptor)) != current.identity:
                    raise ValueError("restored_state_changed")
                os.fsync(descriptor)
                if file_identity(os.fstat(descriptor)) != current.identity:
                    raise ValueError("restored_state_changed")
                os.fsync(parent_fd)
            finally:
                os.close(descriptor)
    final = _state(path)
    if final != current or (
        final is not None and (current is None or final.identity != current.identity)
    ):
        raise ValueError("restored_state_changed")


class _ApplyJournal:
    def __init__(
        self, store: VerifiedChangeStore, record: Record, *, confirmed: bool = False
    ) -> None:
        self.store = store
        self.record = record
        self.confirmed = confirmed

    def save(self, record: Record) -> None:
        self.confirmed = False
        record["updated_at"] = _now()
        self.record = self.store.publish_apply(record)
        self.confirmed = True

    def reload(self) -> None:
        self.confirmed = False
        self.record = self.store.load_apply(self.record["apply_id"])
        sync_directory(self.store.path_for("apply", self.record["apply_id"]))
        self.confirmed = True

    def transition(self, state: str) -> None:
        if self.record["state"] == state:
            if not self.confirmed:
                self.reload()
            return
        record = deepcopy(self.record)
        record["state"] = state
        self.save(record)

    def entry(self, path: str, state: str) -> None:
        record = deepcopy(self.record)
        for entry in record["entries"]:
            if entry["path"] == path:
                entry["state"] = state
        self.save(record)


class ArtifactApplier:
    """Plans and performs the copy of generated files into a repository."""

    def plan(self, artifacts: GeneratedArtifactSet, repo_root: Path) -> list[FileChange]:
        return [self._plan_file(generated, repo_root) for generated in artifacts.files]

    def apply_run(
        self,
        store: VerifiedChangeStore,
        *,
        apply_id: str,
        case_id: str,
        run_id: str,
        run_sha256: str,
        changes_sha256: str,
        quiescence_confirmed: bool = False,
        local_storage_confirmed: bool = False,
        required_assurance: str = "isolated",
    ) -> Record:
        """Apply an explicit ready run with durable ownership and exact-state recovery."""
        if not quiescence_confirmed or not local_storage_confirmed:
            raise ValueError("application_confirmation_required")
        if required_assurance not in {"isolated", "trusted-local"}:
            raise ValueError("invalid_assurance")
        run = store.run(run_id)
        if run["case_id"] != case_id or run["decision"] != "ready":
            raise ValueError("apply_run_not_ready")
        if required_assurance == "isolated" and run["assurance"] != "isolated":
            raise ValueError("assurance_mismatch")
        if run_sha256 != record_digest(run) or changes_sha256 != record_digest(run["changes"]):
            raise ValueError("apply_hash_mismatch")
        directory = store.path_for("apply", apply_id)
        try:
            previous_application = store.load_apply(apply_id)
        except FileNotFoundError:
            previous_application = None
        if previous_application is not None:
            expected = {
                "case_id": case_id,
                "run_id": run_id,
                "run_sha256": run_sha256,
                "changes_sha256": changes_sha256,
            }
            if any(previous_application[key] != value for key, value in expected.items()):
                raise ValueError("application_request_conflict")
            previous_journal = _ApplyJournal(store, previous_application)
            previous_journal.reload()
            return previous_journal.record
        if not run["changes"]:
            raise ValueError("no_changes_to_apply")
        changes: list[FileChange] = []
        states: dict[str, _FileState | None] = {}
        artifacts = {item["artifact_id"]: item for item in run["artifacts"]}
        for change in run["changes"]:
            source = artifacts[change["after_artifact_id"]]
            content = read_regular(
                store.path_for("run", run_id) / source["path"], source["size_bytes"]
            )
            changes.append(
                FileChange(
                    path=change["path"],
                    action=change["action"],
                    content=content.decode("utf-8"),
                    before_sha256=change["before_sha256"],
                    before_mode=change["before_mode"],
                )
            )
        lock = OwnedLock(store.base_path / "locks/apply.lock", run_id).acquire()
        journal: _ApplyJournal | None = None
        preparation_attempted = False
        try:
            self._require_no_pending_application(store)
            if directory.exists() or directory.is_symlink():
                raise ValueError("incomplete_application")
            for change in changes:
                state = _state(resolve_change_path(store.repository, change.path))
                if not _matches(state, change.before_sha256, change.before_mode):
                    raise ValueError(f"apply_conflict: {change.path}")
                states[change.path] = state
            ensure_directory(directory)
            entries: list[Record] = []
            for change, definition in zip(changes, run["changes"], strict=True):
                before = states[change.path]
                backup = f"before/{change.path}" if before is not None else None
                staged = f"staged/{change.path}"
                for relative, payload in (
                    (backup, before.content if before is not None else b""),
                    (staged, change.content.encode("utf-8")),
                ):
                    if relative is not None:
                        target = resolve_within_repository(directory, relative)
                        ensure_directory(target.parent)
                        atomic_write(target, payload, exclusive=True)
                entries.append(
                    {
                        "path": change.path,
                        "before_sha256": change.before_sha256,
                        "after_sha256": definition["after_sha256"],
                        "before_mode": change.before_mode,
                        "after_mode": definition["after_mode"],
                        "backup_path": backup,
                        "staged_path": staged,
                        "state": "prepared",
                    }
                )
            timestamp = _now()
            record: Record = {
                "record_type": "apply",
                "schema_version": "verified-change/1",
                "apply_id": apply_id,
                "case_id": case_id,
                "run_id": run_id,
                "run_sha256": run_sha256,
                "changes_sha256": changes_sha256,
                "created_at": timestamp,
                "updated_at": timestamp,
                "state": "prepared",
                "entries": entries,
                "quiescence_confirmed_at": timestamp,
                "postcheck_at": None,
                "actions": [],
            }
            preparation_attempted = True
            journal = _ApplyJournal(store, store.publish_apply(record), confirmed=True)
            journal.transition("applying")
            try:
                self.write(changes, store.repository, _journal=journal)
                completed = deepcopy(journal.record)
                completed.update(state="applied", postcheck_at=_now())
                journal.save(completed)
            except BaseException as failure:
                journal.reload()
                if journal.record["state"] == "applied":
                    return journal.record
                self._rollback(journal, changes, states, type(failure).__name__)
                if not isinstance(failure, Exception):
                    raise
            return journal.record
        finally:
            unpublished = not preparation_attempted
            if journal is None and preparation_attempted:
                try:
                    with parent_descriptor(directory / "apply.json") as (descriptor, name):
                        os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                except FileNotFoundError:
                    unpublished = True
            if unpublished or (
                journal is not None
                and journal.confirmed
                and journal.record["state"] in {"applied", "rolled_back", "conflict"}
            ):
                lock.release()
            else:
                lock.leave_locked()

    def recover(
        self,
        store: VerifiedChangeStore,
        apply_id: str,
        *,
        local_storage_confirmed: bool = False,
        same_host_confirmed: bool = False,
        quiescence_confirmed: bool = False,
    ) -> Record:
        """Recover an interrupted owned application without replaying its writes."""
        record = store.load_apply(apply_id)
        if record["state"] in {"applied", "rolled_back", "conflict", "unknown"}:
            completed = _ApplyJournal(store, record)
            completed.reload()
            if record["state"] != "unknown" and (
                local_storage_confirmed and same_host_confirmed and quiescence_confirmed
            ):
                self._release_completed_lock(store, completed.record)
            return completed.record
        if not (local_storage_confirmed and same_host_confirmed and quiescence_confirmed):
            raise ValueError("recovery_confirmation_required")
        lock_path = store.base_path / "locks/apply.lock"
        try:
            lock_record = parse_record(read_regular(lock_path, 4096))
        except FileNotFoundError:
            if record["state"] != "prepared":
                raise ValueError("recovery_lock_missing") from None
            lock = OwnedLock(lock_path, record["run_id"]).acquire()
        else:
            lock = OwnedLock.resume(
                lock_path,
                record["run_id"],
                lock_record["nonce"],
                local_storage_confirmed=local_storage_confirmed,
                same_host_confirmed=same_host_confirmed,
                quiescence_confirmed=quiescence_confirmed,
            )
        journal = _ApplyJournal(store, record)
        try:
            journal.reload()
            if journal.record["state"] == "prepared":
                stopped = deepcopy(journal.record)
                stopped["state"] = "conflict"
                stopped["actions"].append(
                    {
                        "code": "application_not_started",
                        "target": apply_id,
                        "message": "Original files unchanged. Export or create a new application.",
                        "retryable": False,
                    }
                )
                journal.save(stopped)
                return journal.record
            directory = store.path_for("apply", apply_id)
            limit = store.case(record["case_id"])["limits"]["max_file_bytes"]
            changes: list[FileChange] = []
            previous: dict[str, _FileState | None] = {}
            for entry in journal.record["entries"]:
                after = read_regular(directory / entry["staged_path"], limit)
                before = (
                    read_regular(directory / entry["backup_path"], limit)
                    if entry["backup_path"] is not None
                    else None
                )
                previous[entry["path"]] = (
                    _FileState(before, entry["before_mode"]) if before is not None else None
                )
                changes.append(
                    FileChange(
                        path=entry["path"],
                        action="update" if before is not None else "create",
                        content=after.decode("utf-8"),
                        before_sha256=entry["before_sha256"],
                        before_mode=entry["before_mode"],
                    )
                )
            self._rollback(journal, changes, previous, "Interrupted application recovered.")
            return journal.record
        finally:
            if journal.confirmed and journal.record["state"] in {
                "applied",
                "rolled_back",
                "conflict",
            }:
                lock.release()
            else:
                lock.leave_locked()

    @staticmethod
    def _require_no_pending_application(
        store: VerifiedChangeStore, *, confirm_run_id: str | None = None
    ) -> None:
        with os.scandir(store.base_path / "applies") as applications:
            for index, item in enumerate(applications):
                if index >= 10_000:
                    raise ValueError("application_record_limit")
                if not item.is_dir(follow_symlinks=False):
                    raise ValueError("unsafe_application_record")
                record = store.load_apply(item.name)
                if record["state"] in {"prepared", "applying", "rolling_back", "unknown"}:
                    raise ValueError(f"application_recovery_required: {item.name}")
                if record["run_id"] == confirm_run_id:
                    sync_directory(store.path_for("apply", item.name))

    def _release_completed_lock(self, store: VerifiedChangeStore, record: Record) -> None:
        path = store.base_path / "locks/apply.lock"
        try:
            owner = parse_record(read_regular(path, 4096))
        except FileNotFoundError:
            return
        if owner["owner_run_id"] != record["run_id"]:
            return
        lock = OwnedLock.resume(
            path,
            record["run_id"],
            owner["nonce"],
            local_storage_confirmed=True,
            same_host_confirmed=True,
            quiescence_confirmed=True,
        )
        confirmed = False
        try:
            self._require_no_pending_application(store, confirm_run_id=record["run_id"])
            confirmed = True
        finally:
            if confirmed:
                lock.release()
            else:
                lock.leave_locked()

    def _rollback(
        self,
        journal: _ApplyJournal,
        changes: list[FileChange],
        previous: dict[str, _FileState | None],
        message: str,
    ) -> None:
        store = journal.store
        apply_id = journal.record["apply_id"]
        try:
            journal.transition("rolling_back")
            for change in changes:
                current = _state(resolve_change_path(store.repository, change.path))
                after_hash = hashlib.sha256(change.content.encode("utf-8")).hexdigest()
                mode = change.before_mode if change.before_mode is not None else 0o644
                if current != previous[change.path] and not _matches(current, after_hash, mode):
                    raise ValueError(f"recovery_unknown: {change.path}")
            self._restore(changes, previous, store.repository, journal)
            for change in changes:
                _confirm_restored(
                    resolve_change_path(store.repository, change.path),
                    previous[change.path],
                    store.repository,
                )
            restored = deepcopy(journal.record)
            for entry in restored["entries"]:
                entry["state"] = "restored"
            restored.update(state="rolled_back", postcheck_at=_now())
            restored["actions"].append(
                {
                    "code": "application_rolled_back",
                    "target": apply_id,
                    "message": message[:2000],
                    "retryable": False,
                }
            )
            journal.save(restored)
        except (OSError, ValueError) as failure:
            journal.reload()
            current_record = journal.record
            if current_record["state"] in {"applied", "rolled_back", "conflict", "unknown"}:
                journal.record = current_record
                return
            unknown = deepcopy(current_record)
            unknown["state"] = "unknown"
            unknown["actions"].append(
                {
                    "code": "recovery_unknown",
                    "target": apply_id,
                    "message": str(failure)[:2000],
                    "retryable": False,
                }
            )
            journal.save(unknown)

    def write(
        self,
        changes: list[FileChange],
        repo_root: Path,
        *,
        force: bool = False,
        backup_dir: Path | None = None,
        _journal: _ApplyJournal | None = None,
    ) -> list[FileChange]:
        """Apply a checked batch; managed runs provide the durable recovery journal."""
        if force:
            raise ValueError("force_disabled: export changes and resolve the conflict")
        if len({change.path for change in changes}) != len(changes):
            raise ValueError("duplicate_apply_path")
        ensure_distinct_paths([change.path for change in changes])
        if any(change.action in {"conflict", "rejected"} for change in changes):
            return []
        previous: dict[str, _FileState | None] = {}
        for change in changes:
            target = resolve_change_path(repo_root, change.path)
            state = _state(target)
            if not _matches(state, change.before_sha256, change.before_mode):
                raise ValueError(f"apply_conflict: {change.path}")
            if change.action == "update" and state is None:
                raise ValueError(f"apply_conflict: {change.path}")
            previous[change.path] = state
        selected = [change for change in changes if change.action in {"create", "update"}]
        if backup_dir is not None:
            if backup_dir.is_symlink():
                raise ValueError("unsafe_backup_directory")
            backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            for change in selected:
                state = previous[change.path]
                if state is None:
                    continue
                saved = resolve_within_repository(backup_dir, change.path)
                saved.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                atomic_write(saved, state.content, mode=0o600, exclusive=True)
        attempted: list[FileChange] = []
        try:
            for change in selected:
                target = resolve_change_path(repo_root, change.path)
                state = _state(target)
                if not _matches(state, change.before_sha256, change.before_mode):
                    raise ValueError(f"apply_conflict: {change.path}")
                ensure_directory(target.parent, mode=0o755)
                target = resolve_change_path(repo_root, change.path)
                attempted.append(change)
                atomic_write(
                    target,
                    change.content.encode("utf-8"),
                    mode=change.before_mode if change.before_mode is not None else 0o644,
                    exclusive=change.action == "create",
                    expected_identity=state.identity if state is not None else None,
                )
                if _journal is not None:
                    _journal.entry(change.path, "written")
            for change in changes:
                current = _state(resolve_change_path(repo_root, change.path))
                expected = (
                    hashlib.sha256(change.content.encode("utf-8")).hexdigest()
                    if change.action != "unchanged"
                    else change.before_sha256
                )
                mode = change.before_mode if change.before_mode is not None else 0o644
                if not _matches(current, expected, mode):
                    raise ValueError(f"apply_postcheck_failed: {change.path}")
        except BaseException:
            if _journal is not None:
                _journal.transition("rolling_back")
            self._restore(attempted, previous, repo_root, _journal)
            raise
        return selected

    @staticmethod
    def _restore(
        attempted: list[FileChange],
        previous: dict[str, _FileState | None],
        repo_root: Path,
        journal: _ApplyJournal | None = None,
    ) -> None:
        for change in reversed(attempted):
            try:
                target = resolve_change_path(repo_root, change.path)
                current = _state(target)
                before = previous[change.path]
                if current == before:
                    _confirm_restored(target, before, repo_root)
                    if journal is not None:
                        journal.entry(change.path, "restored")
                    continue
                mode = before.mode if before is not None else 0o644
                after_hash = hashlib.sha256(change.content.encode("utf-8")).hexdigest()
                if current is None or not _matches(current, after_hash, mode):
                    raise ValueError(f"recovery_unknown: {change.path}")
                if before is None:
                    with parent_descriptor(target) as (descriptor, name):
                        actual = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                        if file_identity(actual) != current.identity:
                            raise ValueError(f"recovery_unknown: {change.path}")
                        os.unlink(name, dir_fd=descriptor)
                    sync_directory(target.parent)
                else:
                    atomic_write(
                        target,
                        before.content,
                        mode=before.mode,
                        expected_identity=current.identity,
                    )
                _confirm_restored(target, before, repo_root)
                if journal is not None:
                    journal.entry(change.path, "restored")
            except (OSError, ValueError) as recovery_failure:
                raise ValueError(f"recovery_unknown: {change.path}") from recovery_failure

    def _plan_file(self, generated: GeneratedFile, repo_root: Path) -> FileChange:
        path, content = generated.path, generated.content
        try:
            target = resolve_change_path(repo_root, path)
            state = _state(target)
        except (OSError, ValueError) as exc:
            return FileChange(path, "rejected", content, str(exc))
        if state is None:
            if not generated.is_new:
                return FileChange(path, "conflict", content, "original file was deleted")
            return FileChange(path, "create", content)
        try:
            current = state.content.decode("utf-8")
        except UnicodeDecodeError:
            return FileChange(path, "conflict", content, "existing file is not readable text")
        if current == content:
            return FileChange(
                path, "unchanged", content, before_sha256=state.sha256, before_mode=state.mode
            )
        if not generated.is_new and current == generated.original_content:
            return FileChange(
                path, "update", content, before_sha256=state.sha256, before_mode=state.mode
            )
        return FileChange(
            path,
            "conflict",
            content,
            "changed in the repository since the run",
            state.sha256,
            state.mode,
        )

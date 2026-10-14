"""Disposable, validated JSON projections; never an authority for a verdict."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from ddk.models.verified_change import Record, canonical_json, record_digest
from ddk.security.file_access import read_regular
from ddk.security.redact import redact_string
from ddk.services.durable_files import ensure_directory

if TYPE_CHECKING:
    from ddk.services.verified_change_store import VerifiedChangeStore

_TABLES: dict[str, str] = {
    "cases": (
        "case_id TEXT PRIMARY KEY,schema_version TEXT NOT NULL,created_at TEXT NOT "
        "NULL,request TEXT NOT NULL,source_origin TEXT NOT NULL,git_base_ref "
        "TEXT,baseline_tree_sha256 TEXT NOT NULL,environment_sha256 TEXT NOT "
        "NULL,evaluator_sha256 TEXT NOT NULL,font_manifest_sha256 "
        "TEXT,container_network_policy TEXT,limits_json TEXT NOT "
        "NULL,fixed_inputs_json TEXT NOT NULL,container_json TEXT NOT "
        "NULL,record_sha256 TEXT NOT NULL,record_json TEXT NOT NULL"
    ),
    "requirements": (
        "case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,requirement_id "
        "TEXT,summary TEXT NOT NULL,allowed_paths_json TEXT NOT NULL,allow_delete "
        "INTEGER NOT NULL CHECK(allow_delete IN (0,1)),PRIMARY "
        "KEY(case_id,requirement_id)"
    ),
    "checks": (
        "case_id TEXT REFERENCES cases(case_id) ON DELETE CASCADE,check_id TEXT,kind "
        "TEXT NOT NULL,required INTEGER NOT NULL,baseline_expectation "
        "TEXT,candidate_expectation TEXT,definition_path TEXT NOT "
        "NULL,definition_sha256 TEXT NOT NULL,command_argv_json TEXT NOT "
        "NULL,report_adapter TEXT NOT NULL,allow_skipped INTEGER NOT NULL,timeout_ms "
        "INTEGER NOT NULL,max_retries INTEGER NOT NULL,viewport_width "
        "INTEGER,viewport_height INTEGER,requirement_ids_json TEXT NOT NULL,PRIMARY "
        "KEY(case_id,check_id)"
    ),
    "runs": (
        "run_id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES "
        "cases(case_id),source_run_id TEXT REFERENCES runs(run_id),operation TEXT "
        "NOT NULL,status TEXT NOT NULL,verdict TEXT,stop_reason TEXT,started_at TEXT "
        "NOT NULL,finished_at TEXT,duration_ms INTEGER,request_sha256 TEXT NOT "
        "NULL,baseline_tree_sha256 TEXT,candidate_tree_sha256 TEXT,latest_round "
        "INTEGER,assurance_level TEXT,total_cost_microusd INTEGER NOT "
        "NULL,reserved_cost_microusd INTEGER NOT NULL,integrity_json TEXT NOT "
        "NULL,actions_json TEXT NOT NULL,record_sha256 TEXT NOT NULL,record_json "
        "TEXT NOT NULL"
    ),
    "run_rounds": (
        "run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,round_no "
        "INTEGER,candidate_tree_sha256 TEXT NOT NULL,changes_sha256 TEXT NOT "
        "NULL,started_at TEXT NOT NULL,finished_at TEXT,PRIMARY KEY(run_id,round_no)"
    ),
    "check_results": (
        "run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,round_no "
        "INTEGER,phase TEXT,check_id TEXT,status TEXT NOT NULL,exit_code "
        "INTEGER,executed_count INTEGER,failed_count INTEGER,skipped_count "
        "INTEGER,duration_ms INTEGER NOT NULL,reason_code TEXT,evidence_origin TEXT "
        "NOT NULL,artifact_ids_json TEXT NOT NULL,PRIMARY "
        "KEY(run_id,round_no,phase,check_id)"
    ),
    "file_changes": (
        "run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,path TEXT,change_kind "
        "TEXT NOT NULL,before_sha256 TEXT,after_sha256 TEXT,before_mode "
        "INTEGER,after_mode INTEGER,size_delta_bytes INTEGER,hunk_count "
        "INTEGER,before_artifact_id TEXT,after_artifact_id TEXT,requirement_ids_json "
        "TEXT NOT NULL,PRIMARY KEY(run_id,path)"
    ),
    "artifacts": (
        "run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,artifact_id TEXT,kind "
        "TEXT NOT NULL,path TEXT NOT NULL,sha256 TEXT NOT NULL,size_bytes INTEGER "
        "NOT NULL,sensitive INTEGER NOT NULL,public_export_allowed INTEGER NOT "
        "NULL,PRIMARY KEY(run_id,artifact_id)"
    ),
    "model_calls": (
        "run_id TEXT REFERENCES runs(run_id) ON DELETE CASCADE,call_id TEXT,round_no "
        "INTEGER NOT NULL,provider_kind TEXT NOT NULL,model TEXT NOT NULL,state TEXT "
        "NOT NULL,input_tokens INTEGER,output_tokens INTEGER,reserved_cost_microusd "
        "INTEGER NOT NULL,actual_cost_microusd INTEGER,prompt_sha256 "
        "TEXT,response_sha256 TEXT,PRIMARY KEY(run_id,call_id)"
    ),
    "apply_transactions": (
        "transaction_id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES "
        "runs(run_id),case_id TEXT NOT NULL REFERENCES cases(case_id),state TEXT NOT "
        "NULL,created_at TEXT NOT NULL,updated_at TEXT,target_root_sha256 "
        "TEXT,applied_root_sha256 TEXT,targets_json TEXT NOT NULL,record_sha256 TEXT "
        "NOT NULL,record_json TEXT NOT NULL"
    ),
    "failure_lessons": (
        "lesson_id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES cases(case_id) "
        "ON DELETE CASCADE,run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE "
        "CASCADE,round_no INTEGER NOT NULL,check_id TEXT NOT NULL,reason_code TEXT "
        "NOT NULL,error_signature_sha256 TEXT NOT NULL,failed_patch_sha256 TEXT NOT "
        "NULL,affected_paths_json TEXT NOT NULL,diagnostic_summary TEXT NOT NULL "
        "CHECK(length(diagnostic_summary)<=4096),created_at TEXT NOT NULL"
    ),
}


_HUNKS_WORKER = r"""import difflib,hashlib,json,os,stat,sys
rows=json.load(sys.stdin)
def content(item):
 if item is None:return b''
 fd=os.open(item['path'],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 with os.fdopen(fd,'rb') as f:
  before=os.fstat(f.fileno())
  if not stat.S_ISREG(before.st_mode) or before.st_nlink!=1:raise ValueError('unsafe_source')
  raw=f.read(item['size_bytes']+1)
  if len(raw)!=item['size_bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
   raise ValueError('source_changed')
 return raw
answer={}
for row in rows:
 a,b=content(row['before']),content(row['after'])
 try:
  if b'\0' in a+b:raise UnicodeError()
  diff=difflib.unified_diff(a.decode('utf-8').splitlines(),b.decode('utf-8').splitlines())
  count=sum(line.startswith('@@') for line in diff)
 except UnicodeError:count=1
 answer[row['path']]=max(1,count)
print(json.dumps(answer))
"""


def _json(value: object) -> str:
    return canonical_json(value).decode()


class VerifiedIndexCatalog:
    """A reconstructable catalog with bounded read-only public queries."""

    tables = (*_TABLES, "failure_lessons_fts")

    def __init__(self, store: VerifiedChangeStore) -> None:
        self.store = store
        self.path = store.base_path / "index.sqlite3"

    @contextmanager
    def _lock(self) -> Generator[None]:
        import fcntl

        from ddk.security.file_access import parent_descriptor

        ensure_directory(self.store.base_path)
        with parent_descriptor(self.store.base_path / "index.lock") as (parent, name):
            fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe_index_path")
            deadline = time.monotonic() + 0.25
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ValueError("catalog_busy_reindex_required") from None
                    time.sleep(0.01)
            yield
        finally:
            os.close(fd)

    @contextmanager
    def _connect(
        self, *, readonly: bool = False, locked: bool = False
    ) -> Generator[sqlite3.Connection]:
        with nullcontext() if locked else self._lock(), self._open(readonly=readonly) as db:
            yield db

    def _safe_files(self) -> None:
        if any(p.is_symlink() for p in self.path.parents):
            raise ValueError("unsafe_index_path")
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.path) + suffix)
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("unsafe_index_path")

    @contextmanager
    def _open(self, *, readonly: bool = False) -> Generator[sqlite3.Connection]:
        self._safe_files()
        if not readonly:
            ensure_directory(self.path.parent)
        connection = sqlite3.connect(
            self.path.as_uri() + "?mode=ro" if readonly else self.path, uri=readonly, timeout=5
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.execute("PRAGMA synchronous=NORMAL")
            if not readonly:
                self.path.chmod(0o600)
                connection.execute("PRAGMA journal_mode=WAL")
                for name, columns in _TABLES.items():
                    connection.execute(f"CREATE TABLE IF NOT EXISTS {name} ({columns})")
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS lesson_lookup "
                    "ON failure_lessons(case_id,check_id,created_at DESC,lesson_id)"
                )
                connection.execute(
                    "CREATE VIRTUAL TABLE IF NOT EXISTS failure_lessons_fts "
                    "USING fts5(check_id,reason_code,affected_paths_json,diagnostic_summary,"
                    "content='failure_lessons',content_rowid='rowid')"
                )
            yield connection
            if not readonly:
                connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _put(db: sqlite3.Connection, table: str, row: Record, key: str) -> None:
        names = list(row)
        updates = ",".join(f"{name}=excluded.{name}" for name in names if name != key)
        db.execute(
            f"INSERT INTO {table} ({','.join(names)}) "
            f"VALUES ({','.join('?' for _ in names)}) "
            f"ON CONFLICT({key}) DO UPDATE SET {updates}",
            tuple(row.values()),
        )

    @staticmethod
    def _child(db: sqlite3.Connection, table: str, row: Record) -> None:
        db.execute(
            f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
            tuple(row.values()),
        )

    def _case(self, db: sqlite3.Connection, case: Record) -> None:
        ident = case["case_id"]
        environment: Record = {}
        for item in case["inputs"]:
            if item["role"] == "environment" and item["path"].endswith(".json"):
                from ddk.models.verified_change import decode_json

                try:
                    value = decode_json(
                        read_regular(
                            self.store.path_for("case", ident) / "inputs" / item["path"],
                            item["size_bytes"],
                        )
                    )
                except ValueError:
                    continue
                if value.get("record_type") == "environment":
                    environment = value
        self._put(
            db,
            "cases",
            {
                "case_id": ident,
                "schema_version": case["schema_version"],
                "created_at": case["created_at"],
                "request": case["request"],
                "source_origin": case.get("source_origin", "directory"),
                "git_base_ref": case.get("git_base_ref"),
                "baseline_tree_sha256": case["baseline_tree_sha256"],
                "environment_sha256": case["environment_sha256"],
                "evaluator_sha256": case["evaluator_sha256"],
                "font_manifest_sha256": environment.get("font_manifest_sha256"),
                "container_network_policy": None,
                "limits_json": _json(case["limits"]),
                "fixed_inputs_json": _json(case["inputs"]),
                "container_json": _json(
                    {
                        k: environment[k]
                        for k in ("app_image_sha256", "checker_image_sha256")
                        if k in environment
                    }
                ),
                "record_sha256": record_digest(case),
                "record_json": _json(case),
            },
            "case_id",
        )
        for table in ("requirements", "checks"):
            db.execute(f"DELETE FROM {table} WHERE case_id=?", (ident,))
        for r in case["requirements"]:
            self._child(
                db,
                "requirements",
                {
                    "case_id": ident,
                    "requirement_id": r["requirement_id"],
                    "summary": r["description"],
                    "allowed_paths_json": _json(r.get("allowed_paths", case["scope_paths"])),
                    "allow_delete": int(r.get("allow_delete", False)),
                },
            )
        for c in case["checks"]:
            vp: Record = c["viewport"] or {}
            self._child(
                db,
                "checks",
                {
                    "case_id": ident,
                    "check_id": c["check_id"],
                    "kind": c["kind"],
                    "required": int(c["required"]),
                    "baseline_expectation": "pass" if c["role"] == "preserve" else None,
                    "candidate_expectation": "pass",
                    "definition_path": c["definition_path"],
                    "definition_sha256": c["definition_sha256"],
                    "command_argv_json": _json(c["command_argv"]),
                    "report_adapter": c.get("report_adapter", "ddk-json"),
                    "allow_skipped": int(c.get("allow_skipped", False)),
                    "timeout_ms": c["timeout_ms"],
                    "max_retries": 0,
                    "viewport_width": vp.get("width"),
                    "viewport_height": vp.get("height"),
                    "requirement_ids_json": _json(
                        [
                            r["requirement_id"]
                            for r in case["requirements"]
                            if c["check_id"] in r["check_ids"]
                        ]
                    ),
                },
            )

    def upsert_case(self, record: Record) -> None:
        with self._connect() as db:
            self._case(db, self.store.case(record["case_id"]))

    def _hunks(self, case: Record, run: Record) -> dict[str, int]:
        from ddk.models.verified_change import decode_json

        before = {i["path"]: i for i in case["inputs"] if i["role"] == "source"}
        after = {a["artifact_id"]: a for a in run["artifacts"]}
        rows: list[Record] = []
        for c in run["changes"]:
            old, new = before.get(c["path"]), after.get(c["after_artifact_id"])
            if c["after_sha256"] is not None and new is None:
                continue
            rows.append(
                {
                    "path": c["path"],
                    "before": {
                        "path": str(
                            self.store.path_for("case", case["case_id"]) / "inputs" / c["path"]
                        ),
                        "size_bytes": old["size_bytes"],
                        "sha256": old["sha256"],
                    }
                    if old
                    else None,
                    "after": {
                        "path": str(self.store.path_for("run", run["run_id"]) / new["path"]),
                        "size_bytes": new["size_bytes"],
                        "sha256": new["sha256"],
                    }
                    if new
                    else None,
                }
            )
        if not rows:
            return {}
        with tempfile.TemporaryDirectory(prefix="ddk-index-diff-") as folder:
            try:
                result = subprocess.run(
                    [sys.executable, "-I", "-c", _HUNKS_WORKER],
                    input=canonical_json(rows),
                    capture_output=True,
                    timeout=1,
                    cwd=folder,
                    check=False,
                )
            except subprocess.TimeoutExpired as error:
                raise ValueError("catalog_diff_timeout") from error
        if result.returncode != 0:
            raise ValueError("catalog_diff_unavailable")
        values = decode_json(result.stdout)
        if set(values) != {r["path"] for r in rows} or any(
            type(n) is not int or n < 1 for n in values.values()
        ):
            raise ValueError("catalog_diff_invalid")
        return {p: int(n) for p, n in values.items()}

    def _run(self, db: sqlite3.Connection, run: Record, depth: int = 0) -> None:
        if depth >= 32:
            raise ValueError("source_run_depth")
        case = self.store.case(run["case_id"])
        self._case(db, case)
        if run["source_run_id"]:
            self._run(db, self.store.run(run["source_run_id"]), depth + 1)
        ident = run["run_id"]
        calls = run["model_calls"]
        self._put(
            db,
            "runs",
            {
                "run_id": ident,
                "case_id": run["case_id"],
                "source_run_id": run["source_run_id"],
                "operation": run["operation"],
                "status": run["status"],
                "verdict": run["decision"],
                "stop_reason": next((a["code"] for a in run["actions"]), None),
                "started_at": run["started_at"],
                "finished_at": run["finished_at"],
                "duration_ms": run["duration_ms"],
                "request_sha256": run["request_sha256"],
                "baseline_tree_sha256": case["baseline_tree_sha256"],
                "candidate_tree_sha256": run["candidate_tree_sha256"],
                "latest_round": run["latest_round"],
                "assurance_level": run["assurance"],
                "total_cost_microusd": sum(
                    c.get("calculated_micro_usd") or 0 for c in calls if c["state"] == "settled"
                ),
                "reserved_cost_microusd": sum(
                    c["reserved_micro_usd"] for c in calls if c["state"] != "settled"
                ),
                "integrity_json": _json(run["integrity"]),
                "actions_json": _json(run["actions"]),
                "record_sha256": record_digest(run),
                "record_json": _json(run),
            },
            "run_id",
        )
        for table in (
            "run_rounds",
            "check_results",
            "file_changes",
            "artifacts",
            "model_calls",
            "failure_lessons",
        ):
            db.execute(f"DELETE FROM {table} WHERE run_id=?", (ident,))
        for r in run["rounds"]:
            self._child(db, "run_rounds", {"run_id": ident, **r})
        for r in run["results"]:
            self._child(
                db,
                "check_results",
                {
                    "run_id": ident,
                    **{k: v for k, v in r.items() if k not in ("artifact_ids", "retry_count")},
                    "artifact_ids_json": _json(r["artifact_ids"]),
                },
            )
        baseline = {i["path"]: i for i in case["inputs"] if i["role"] == "source"}
        artifacts = {a["artifact_id"]: a for a in run["artifacts"]}
        hunks = self._hunks(case, run)
        for r in run["changes"]:
            original = baseline.get(r["path"])
            proposed = artifacts.get(r["after_artifact_id"])
            before_size = original["size_bytes"] if original else 0
            after_size = proposed["size_bytes"] if proposed else 0
            self._child(
                db,
                "file_changes",
                {
                    "run_id": ident,
                    "path": r["path"],
                    "change_kind": {"create": "added", "update": "modified", "delete": "deleted"}[
                        r["action"]
                    ],
                    "before_sha256": r["before_sha256"],
                    "after_sha256": r["after_sha256"],
                    "before_mode": r["before_mode"],
                    "after_mode": r["after_mode"],
                    "size_delta_bytes": after_size - before_size
                    if proposed or r["after_sha256"] is None
                    else None,
                    "hunk_count": hunks.get(r["path"]),
                    "before_artifact_id": None,
                    "after_artifact_id": r["after_artifact_id"],
                    "requirement_ids_json": _json(r["requirement_ids"]),
                },
            )
        for r in run["artifacts"]:
            self._child(db, "artifacts", {"run_id": ident, **r})
        for r in calls:
            self._child(
                db,
                "model_calls",
                {
                    "run_id": ident,
                    "call_id": r["call_id"],
                    "round_no": r["round_no"],
                    "provider_kind": r["provider"],
                    "model": r["model"],
                    "state": r["state"],
                    "input_tokens": r.get("input_tokens"),
                    "output_tokens": r.get("output_tokens"),
                    "reserved_cost_microusd": r["reserved_micro_usd"],
                    "actual_cost_microusd": r.get("calculated_micro_usd"),
                    "prompt_sha256": next(
                        (
                            a["sha256"]
                            for a in run["artifacts"]
                            if a["path"] == f"artifacts/prompts/round-{r['round_no']}.json"
                        ),
                        None,
                    ),
                    "response_sha256": next(
                        (
                            a["sha256"]
                            for a in run["artifacts"]
                            if a["path"] == f"artifacts/proposals/{r['call_id']}.json"
                        ),
                        None,
                    ),
                },
            )
        if run["operation"] == "repair":
            self._lessons(db, run)
        db.execute("INSERT INTO failure_lessons_fts(failure_lessons_fts) VALUES('rebuild')")

    def _lessons(self, db: sqlite3.Connection, run: Record) -> None:
        failures = [r for r in run["results"] if r["status"] == "failed"]
        failures += [
            {
                "check_id": "repair",
                "round_no": run["latest_round"] or 0,
                "reason_code": a["code"],
                "artifact_ids": [],
            }
            for a in run["actions"]
            if a["code"] in {"repair_no_progress", "repair_outside_scope"}
        ]
        artifacts = {r["artifact_id"]: r for r in run["artifacts"]}
        rounds = {r["round_no"]: r for r in run["rounds"]}
        for result in failures:
            summary = result["reason_code"] or "check_failed"
            for key in result["artifact_ids"]:
                a = artifacts.get(key)
                if a and a["kind"] in {"log", "data", "ax_snapshot"}:
                    raw = read_regular(
                        self.store.path_for("run", run["run_id"]) / a["path"], a["size_bytes"]
                    )
                    summary += "\n" + redact_string(raw.decode("utf-8", errors="replace"))[:4096]
            summary = redact_string(summary)[:4096]
            reason = result["reason_code"] or "check_failed"
            seed = [
                run["run_id"],
                result["round_no"],
                result.get("phase", "repair"),
                result["check_id"],
                reason,
            ]
            lesson = str(UUID(bytes=hashlib.sha256(canonical_json(seed)).digest()[:16], version=4))
            patch = (
                rounds.get(result["round_no"], {}).get("candidate_tree_sha256")
                or run["candidate_tree_sha256"]
                or record_digest([])
            )
            if result["check_id"] == "repair":
                proposals = [
                    a for a in run["artifacts"] if a["path"].startswith("artifacts/proposals/")
                ]
                if proposals:
                    patch = proposals[-1]["sha256"]
            row = {
                "lesson_id": lesson,
                "case_id": run["case_id"],
                "run_id": run["run_id"],
                "round_no": result["round_no"],
                "check_id": result["check_id"],
                "reason_code": reason,
                "error_signature_sha256": hashlib.sha256(summary.encode()).hexdigest(),
                "failed_patch_sha256": patch,
                "affected_paths_json": _json(sorted(r["path"] for r in run["changes"])),
                "diagnostic_summary": summary,
                "created_at": run["started_at"],
            }
            self._put(db, "failure_lessons", row, "lesson_id")

    def upsert_run(self, record: Record) -> None:
        with self._connect() as db:
            self._run(db, self.store.status(record["run_id"]))

    def _transaction(self, db: sqlite3.Connection, verified: Record) -> None:
        self._run(db, self.store.run(verified["run_id"]))
        self._put(
            db,
            "apply_transactions",
            {
                "transaction_id": verified["apply_id"],
                "run_id": verified["run_id"],
                "case_id": verified["case_id"],
                "state": verified["state"],
                "created_at": verified["created_at"],
                "updated_at": verified.get("updated_at"),
                "target_root_sha256": record_digest(
                    [
                        {"path": e["path"], "sha256": e["before_sha256"], "mode": e["before_mode"]}
                        for e in sorted(verified["entries"], key=lambda row: row["path"])
                    ]
                ),
                "applied_root_sha256": record_digest(
                    [
                        {"path": e["path"], "sha256": e["after_sha256"], "mode": e["after_mode"]}
                        for e in sorted(verified["entries"], key=lambda row: row["path"])
                    ]
                ),
                "targets_json": _json(verified["entries"]),
                "record_sha256": record_digest(verified),
                "record_json": _json(verified),
            },
            "transaction_id",
        )

    def upsert_transaction(self, record: Record) -> None:
        with self._connect() as db:
            self._transaction(db, self.store.load_apply(record["apply_id"]))

    def reindex_all(self) -> Record:
        """Publish a fully validated rebuild while all catalog clients share a lock."""
        from ddk.services.durable_files import sync_directory

        with self._lock():
            cases = [
                self.store.case(p.name)
                for p in sorted((self.store.base_path / "cases").iterdir())
                if p.is_dir()
            ]
            runs = [
                self.store.status(p.name)
                for p in sorted((self.store.base_path / "runs").iterdir())
                if p.is_dir()
            ]
            applies = [
                self.store.load_apply(p.name)
                for p in sorted((self.store.base_path / "applies").iterdir())
                if p.is_dir()
            ]
            original = self.path
            temporary = original.with_name("index-rebuild-" + uuid4().hex + ".sqlite3")
            try:
                self.path = temporary
                with self._connect(locked=True) as db:
                    for case in cases:
                        self._case(db, case)
                    for run in runs:
                        self._run(db, run)
                    for record in applies:
                        self._transaction(db, record)
                with self._connect(readonly=True, locked=True) as db:
                    if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise ValueError("catalog_integrity_failed")
                self.path = original
                self._safe_files()
                with temporary.open("rb") as data:
                    os.fsync(data.fileno())
                os.replace(temporary, original)
                for suffix in ("-wal", "-shm"):
                    sidecar = Path(str(original) + suffix)
                    if sidecar.is_symlink():
                        raise ValueError("unsafe_index_path")
                    sidecar.unlink(missing_ok=True)
                sync_directory(original.parent)
            finally:
                self.path = original
                for suffix in ("", "-wal", "-shm"):
                    Path(str(temporary) + suffix).unlink(missing_ok=True)
        return {"cases": len(cases), "runs": len(runs), "apply_transactions": len(applies)}

    def query(
        self, table: str, *, limit: int = 100, columns: set[str] | None = None
    ) -> list[Record]:
        if table not in self.tables or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("invalid_catalog_query")
        if not self.path.exists():
            return []
        with self._connect(readonly=True) as db:
            info = list(db.execute(f"PRAGMA table_info({table})"))
            names = {row[1] for row in info}
            selected = names if columns is None else names & columns
            if not selected:
                raise ValueError("catalog_columns_required")
            ordering = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
            if not ordering:
                ordering = sorted(names)
            return [
                dict(row)
                for row in db.execute(
                    f"SELECT {','.join(sorted(selected))} FROM {table} "
                    f"ORDER BY {','.join(ordering)} LIMIT ?",
                    (limit,),
                )
            ]

    def lessons(self, case_id: str, check_id: str, query: str = "") -> list[Record]:
        if not self.path.exists():
            return []
        try:
            with self._connect(readonly=True) as db:
                tokens = re.findall(r"\w+", query)[:16]
                if tokens:
                    phrase = " OR ".join('"' + t + '"' for t in tokens)
                    rows = db.execute(
                        "SELECT l.* FROM failure_lessons l "
                        "JOIN failure_lessons_fts f ON l.rowid=f.rowid "
                        "WHERE failure_lessons_fts MATCH ? AND l.case_id=? AND l.check_id=? "
                        "ORDER BY rank,l.lesson_id LIMIT 3",
                        (phrase, case_id, check_id),
                    )
                else:
                    rows = db.execute(
                        "SELECT * FROM failure_lessons WHERE case_id=? AND check_id=? "
                        "ORDER BY created_at DESC,lesson_id LIMIT 3",
                        (case_id, check_id),
                    )
                return [dict(row) for row in rows]
        except (sqlite3.Error, OSError, ValueError):
            logging.getLogger(__name__).warning("catalog_lessons_unavailable: reindex recommended")
            return []

    def dump(self) -> dict[str, list[Record]]:
        with self._connect(readonly=True) as db:
            return {
                table: sorted(
                    [dict(row) for row in db.execute(f"SELECT * FROM {table}")], key=_json
                )
                for table in _TABLES
            }


def sync_index(store: VerifiedChangeStore, operation: str, record: Record) -> None:
    try:
        getattr(VerifiedIndexCatalog(store), operation)(record)
    except (sqlite3.Error, OSError, ValueError, KeyError):
        logging.getLogger(__name__).warning("catalog_sync_failed: reindex required")

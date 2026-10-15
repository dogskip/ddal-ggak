"""Current-source sentinels backed by canonical records, never by SQLite verdicts."""

from __future__ import annotations

import re
import subprocess
from datetime import datetime
from pathlib import Path

from ddk.models.verified_change import Record, decode_json, record_digest, validate_structure
from ddk.security.file_access import read_regular
from ddk.services.case_discovery import configuration_binding
from ddk.services.source_snapshot import capture_git_source, capture_git_worktree
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore


def run_headers(store: VerifiedChangeStore) -> list[Record]:
    root = store.base_path / "runs"
    if not root.exists():
        return []
    records: list[Record] = []
    for directory in sorted(root.iterdir()):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError("unsafe_run_directory")
        store.path_for("run", directory.name)
        path = directory / "run.json"
        if not path.exists():
            path = directory / ".pending/run.json"
        record = decode_json(read_regular(path, 2 * 1024**2))
        validate_structure(record)
        if record["record_type"] != "run" or record["run_id"] != directory.name:
            raise ValueError("run_identity_mismatch")
        records.append(record)
        if len(records) > 10000:
            raise ValueError("run_count_limit")
    return records


def latest_runs(records: list[Record], case_id: str | None = None) -> list[Record]:
    candidates = [r for r in records if case_id is None or r["case_id"] == case_id]
    if not candidates:
        return []
    newest = max(datetime.fromisoformat(r["started_at"]) for r in candidates)
    return sorted(
        [r for r in candidates if datetime.fromisoformat(r["started_at"]) == newest],
        key=lambda row: str(row["run_id"]),
    )


def expected_manifest(case: Record, run: Record) -> list[Record]:
    files = {
        item["path"]: {k: item[k] for k in ("path", "sha256", "mode", "size_bytes")}
        for item in case["inputs"]
        if item["role"] == "source"
    }
    if record_digest([files[p] for p in sorted(files)]) != case["baseline_tree_sha256"]:
        raise ValueError("baseline_mismatch")
    artifacts = {a["artifact_id"]: a for a in run["artifacts"]}
    for change in run["changes"]:
        if change["after_sha256"] is None:
            files.pop(change["path"], None)
        else:
            files[change["path"]] = {
                "path": change["path"],
                "sha256": change["after_sha256"],
                "mode": change["after_mode"],
                "size_bytes": artifacts[change["after_artifact_id"]]["size_bytes"],
            }
    manifest = [files[p] for p in sorted(files)]
    if record_digest(manifest) != run["candidate_tree_sha256"]:
        raise ValueError("candidate_manifest_mismatch")
    return manifest


def gate_status(
    repository: Path, *, case_id: str | None = None, run_id: str | None = None
) -> Record:
    result: Record = {
        "gate_status": "blocked",
        "changed_paths": [],
        "actions": [],
        "read_only": True,
    }

    def blocked(code: str) -> Record:
        result["actions"] = [
            {"code": code, "message": "Verify the current approved case and source."}
        ]
        return result

    try:
        store = VerifiedChangeStore(repository, create=False)
        if case_id is not None:
            store.case(case_id)
        headers = run_headers(store)
        selected = next((r for r in headers if r["run_id"] == run_id), None) if run_id else None
        if run_id and (selected is None or (case_id and selected["case_id"] != case_id)):
            return blocked("gate_run_missing")
        newest = latest_runs(headers, selected["case_id"] if selected else case_id)
        if not newest:
            return blocked("gate_run_missing")
        if selected and all(r["run_id"] != run_id for r in newest):
            return blocked("gate_run_superseded")
        if len(newest) != 1 and selected is None:
            return blocked("gate_selection_ambiguous")
        run = store.status((selected or newest[0])["run_id"])
        result.update(run_id=run["run_id"], case_id=run["case_id"])
        if run["status"] != "completed" or run["decision"] != "ready":
            return blocked("gate_run_not_ready")
        from ddk.services.verified_budget import audit_run_costs

        audit_run_costs(store, run)
        case = store.case(run["case_id"])
        fixed = {f.path: f for f in VerifiedChangeEngine(store).fixed_inputs(case)}
        binding_file = fixed.get("criteria/bootstrap.json")
        if binding_file is None:
            return blocked("gate_binding_missing")
        binding = decode_json(binding_file.content)
        current_binding = configuration_binding(
            repository, explicit=binding.get("origin") == "explicit"
        )
        changed = [
            p
            for p in current_binding["files"]
            if current_binding["files"][p] != binding.get("files", {}).get(p)
        ]
        expected = {r["path"]: r for r in expected_manifest(case, run)}
        limits = {
            "max_file_bytes": case["limits"]["max_file_bytes"],
            "max_total_bytes": case["limits"]["max_artifact_bytes"],
        }
        current = capture_git_worktree(repository, **limits)
        actual = {f.path: f.manifest_entry() for f in current.files}
        changed += [
            p for p in sorted(set(expected) | set(actual)) if expected.get(p) != actual.get(p)
        ]
        if current_binding != binding and not changed:
            changed = ["criteria/bootstrap.json"]
        if capture_git_worktree(repository, **limits).tree_sha256 != current.tree_sha256:
            return blocked("working_tree_changed")
        final_binding = configuration_binding(
            repository, explicit=binding.get("origin") == "explicit"
        )
        changed += [
            p
            for p in final_binding["files"]
            if final_binding["files"][p] != binding.get("files", {}).get(p)
        ]
        if final_binding != binding and not changed:
            changed = ["criteria/bootstrap.json"]
        selection_case = selected["case_id"] if selected else case_id
        initial_headers = [
            r for r in headers if selection_case is None or r["case_id"] == selection_case
        ]
        final_headers = [
            r
            for r in run_headers(store)
            if selection_case is None or r["case_id"] == selection_case
        ]
        initial_digests = {r["run_id"]: record_digest(r) for r in initial_headers}
        final_digests = {r["run_id"]: record_digest(r) for r in final_headers}
        if record_digest(initial_digests) != record_digest(final_digests):
            return blocked("gate_evidence_changed")
        if store.status(run["run_id"]) != run or store.case(case["case_id"]) != case:
            return blocked("gate_evidence_changed")
        result.update(
            gate_status="reopened" if changed else "passed",
            changed_paths=sorted(set(changed)),
            case_sha256=run["case_sha256"],
            bound_tree_sha256=run["candidate_tree_sha256"],
            evaluator_sha256=run["evaluator_sha256"],
            assurance=run["assurance"],
        )
        return blocked("DDK_GATE_REOPENED") if changed else result
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        return blocked("gate_evidence_invalid")


def pre_push_status(repository: Path, updates: bytes) -> Record:
    """Verify every proposed commit tip received through Git's pre-push input."""
    result: Record = {
        "gate_status": "blocked",
        "changed_paths": [],
        "read_only": True,
        "actions": [],
    }
    try:
        if len(updates) > 2 * 1024**2:
            raise ValueError("gate_push_input_limit")
        lines = updates.decode("utf-8", errors="strict").splitlines()
        if not lines or len(lines) > 64:
            raise ValueError("gate_push_updates_required")
        tips: set[str] = set()
        for line in lines:
            fields = line.split()
            if len(fields) != 4 or any(
                re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", fields[i]) is None for i in (1, 3)
            ):
                raise ValueError("gate_push_input_invalid")
            if not fields[0].startswith("refs/") or not fields[2].startswith("refs/"):
                raise ValueError("gate_push_input_invalid")
            if set(fields[1]) == {"0"}:
                raise ValueError("gate_push_deletion_requires_review")
            tips.add(fields[1])
        result = gate_status(repository)
        if result["gate_status"] != "passed":
            return result
        store = VerifiedChangeStore(repository, create=False)
        run = store.status(result["run_id"])
        case = store.case(run["case_id"])
        expected = {r["path"]: r for r in expected_manifest(case, run)}
        changed: set[str] = set()
        for tip in sorted(tips):
            snapshot = capture_git_source(
                repository,
                tip,
                max_file_bytes=case["limits"]["max_file_bytes"],
                max_total_bytes=case["limits"]["max_artifact_bytes"],
            )
            actual = {f.path: f.manifest_entry() for f in snapshot.files}
            changed.update(
                p for p in set(expected) | set(actual) if expected.get(p) != actual.get(p)
            )
        final = gate_status(repository)
        if final["gate_status"] != "passed":
            return final
        if any(
            final.get(key) != result.get(key)
            for key in ("run_id", "case_id", "case_sha256", "evaluator_sha256", "bound_tree_sha256")
        ):
            result.update(
                gate_status="blocked",
                actions=[
                    {
                        "code": "gate_evidence_changed",
                        "message": "The selected verification changed during commit inspection.",
                    }
                ],
            )
            return result
        result.update(push_tips=sorted(tips), changed_paths=sorted(changed))
        if changed:
            result.update(
                gate_status="reopened",
                actions=[
                    {
                        "code": "gate_push_tree_unverified",
                        "message": "Verify the exact commit tips before pushing.",
                    }
                ],
            )
        return result
    except (ValueError, OSError, KeyError, subprocess.SubprocessError):
        result.update(
            gate_status="blocked",
            actions=[
                {
                    "code": "gate_push_input_invalid",
                    "message": "Provide bounded Git pre-push updates for verified commit tips.",
                }
            ],
        )
        return result

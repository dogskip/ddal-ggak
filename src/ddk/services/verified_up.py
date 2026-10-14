"""One owned invocation over the existing canonical services and execution grants."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from ddk.models.verified_change import Record, application_changes, record_digest
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.durable_files import ensure_directory
from ddk.services.source_snapshot import (
    capture_git_source,
    capture_git_worktree,
    materialize_snapshot,
)
from ddk.services.verified_budget import VerifiedPrice
from ddk.services.verified_change_service import VerifiedChangeService
from ddk.services.verified_repair import RepairProvider


async def up(
    repository: Path,
    request: str | None = None,
    *,
    case_id: str | None = None,
    git_base: str = "HEAD",
    dry_run: bool = False,
    repair: bool = False,
    apply: bool = False,
    trusted_local_approved: bool = False,
    provider_approved: bool = False,
    provider: RepairProvider | None = None,
    price: VerifiedPrice | None = None,
    input_limit: int = 32000,
    output_limit: int = 4096,
    quiescence_confirmed: bool = False,
    local_storage_confirmed: bool = False,
) -> Record:
    service = VerifiedChangeService(repository)
    if case_id is None:
        case = await CaseBootstrapper(repository).initialize(
            request or "Verify current changes", git_base=git_base, dry_run=dry_run
        )
        if case.get("status") == "blocked" or dry_run:
            return {
                **case,
                "dry_run": dry_run,
                "workflow": [
                    "snapshot",
                    "verify",
                    *(["repair"] if repair else []),
                    "export",
                    "apply" if apply else "apply-preview",
                ],
            }
        case_id = case["case_id"]
    else:
        case = service.store.case(case_id)
    assert case_id is not None
    if dry_run:
        return {
            "status": "ready",
            "dry_run": True,
            "case_id": case_id,
            "git_base": git_base,
            "checks": case["checks"],
            "scope_paths": case["scope_paths"],
            "requires_trusted_local": case["assurance_required"] == "trusted-local",
            "provider_approved": False,
            "apply_requested": apply,
            "actions": [],
        }
    before = capture_git_source(
        repository,
        git_base,
        max_file_bytes=case["limits"]["max_file_bytes"],
        max_total_bytes=case["limits"]["max_artifact_bytes"],
    )
    current = capture_git_worktree(
        repository,
        max_file_bytes=case["limits"]["max_file_bytes"],
        max_total_bytes=case["limits"]["max_artifact_bytes"],
    )
    old = {f.path: f.sha256 for f in before.files}
    new = {f.path: f.sha256 for f in current.files}
    paths = [p for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)]
    links = {
        p: [
            r["requirement_id"]
            for r in case["requirements"]
            if p in r.get("allowed_paths", case["scope_paths"])
        ]
        for p in paths
    }
    result = await service.verify(
        case_id,
        run_id=str(uuid4()),
        git_base=git_base,
        change_requirements=links,
        trusted_local_approved=trusted_local_approved,
    )
    source = result
    if result["decision"] != "ready" and repair:
        if not provider_approved or provider is None or price is None:
            raise ValueError("provider_confirmation_and_price_required")
        with tempfile.TemporaryDirectory(prefix="ddk-up-") as directory:
            root = Path(directory).resolve()
            baseline = root / "baseline"
            candidate = root / "candidate"
            materialize_snapshot(before, baseline)
            materialize_snapshot(current, candidate)
            result = await service.repair(
                source["run_id"],
                baseline=baseline,
                candidate=candidate,
                run_id=str(uuid4()),
                price=price,
                input_limit=input_limit,
                output_limit=output_limit,
                provider=provider,
                provider_approved=True,
                trusted_local_approved=trusted_local_approved,
            )
    if (
        capture_git_worktree(
            repository,
            max_file_bytes=case["limits"]["max_file_bytes"],
            max_total_bytes=case["limits"]["max_artifact_bytes"],
        ).tree_sha256
        != current.tree_sha256
    ):
        return {
            "status": "blocked",
            "run_id": result["run_id"],
            "decision": result["decision"],
            "actions": [
                {
                    "code": "working_tree_changed",
                    "target": "repository",
                    "message": "Review the current source before applying.",
                }
            ],
        }
    answer: Record = {
        "status": "ready" if result["decision"] == "ready" else "blocked",
        "case_id": case_id,
        "run_id": result["run_id"],
        "source_run_id": source["run_id"],
        "decision": result["decision"],
        "assurance": result["assurance"],
        "actions": result["actions"],
        "apply_preview": application_changes(case, result, source),
    }
    if result["decision"] == "ready":
        destination = service.store.base_path / "exports" / f"{result['run_id']}.zip"
        ensure_directory(destination.parent)
        answer["export"] = service.export(result["run_id"], destination)
        if apply:
            answer["application"] = service.apply(
                apply_id=str(uuid4()),
                case_id=case_id,
                run_id=result["run_id"],
                run_sha256=record_digest(result),
                changes_sha256=record_digest(result["changes"]),
                quiescence_confirmed=quiescence_confirmed,
                local_storage_confirmed=local_storage_confirmed,
                required_assurance=case["assurance_required"],
                target_run_id=source["run_id"],
            )
            if answer["application"]["state"] != "applied":
                answer["status"] = "blocked"
                answer["actions"] = [*answer["actions"], *answer["application"]["actions"]]
    return answer

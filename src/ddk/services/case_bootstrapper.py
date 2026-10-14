"""Compile explicit acceptance definitions and observed bytes into immutable cases."""

from __future__ import annotations

import copy
import hashlib
import tomllib
from pathlib import Path
from uuid import uuid4

from ddk.models.verified_change import (
    Record,
    canonical_json,
    decode_json,
    object_records,
    string_values,
    validate_record,
)
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import normalize_change_path
from ddk.services.source_snapshot import (
    SnapshotFile,
    capture_git_source,
    capture_git_worktree,
    capture_source,
    manifest_digest,
    resolve_git_ref,
)
from ddk.services.verified_change_engine import record_time
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_host import observe_environment, observe_tools

DEFAULT_LIMITS: dict[str, int] = {
    "step_timeout_ms": 30000,
    "run_timeout_ms": 180000,
    "cleanup_timeout_ms": 10000,
    "max_fix_attempts": 2,
    "max_provider_requests": 2,
    "budget_micro_usd": 1000000,
    "max_file_bytes": 2 * 1024**2,
    "max_output_bytes": 10 * 1024**2,
    "max_artifact_bytes": 200 * 1024**2,
    "max_changed_files": 100,
    "cpu_millis_per_worker": 1000,
    "memory_bytes_per_worker": 2 * 1024**3,
    "max_processes_per_worker": 256,
    "browser_shm_bytes": 256 * 1024**2,
}


def _file(path: str, content: bytes, mode: int = 0o644) -> SnapshotFile:
    return SnapshotFile(path, content, hashlib.sha256(content).hexdigest(), mode, len(content))


def configuration_for(repository: Path) -> Record:
    path = repository / ".ddk/verify.toml"
    if path.is_file():
        return tomllib.loads(read_regular(path, 2 * 1024**2).decode())
    path = repository / "ddk.toml"
    if path.is_file():
        return tomllib.loads(read_regular(path, 2 * 1024**2).decode())
    path = repository / "pyproject.toml"
    if path.is_file():
        value = tomllib.loads(read_regular(path, 2 * 1024**2).decode())
        return dict(value.get("tool", {}).get("ddk", {}).get("verify", {}))
    return {}


class CaseBootstrapper:
    def __init__(self, repository: Path) -> None:
        self.repository = repository.resolve()

    async def initialize(
        self,
        request: str,
        *,
        git_base: str = "HEAD",
        baseline: Path | None = None,
        configuration: Record | None = None,
        from_design: Path | None = None,
        dry_run: bool = False,
        observed_environment: tuple[Record, str | None] | None = None,
        supersedes_case_id: str | None = None,
    ) -> Record:
        config = copy.deepcopy(
            configuration if configuration is not None else configuration_for(self.repository)
        )
        if from_design is not None:
            design = decode_json(read_regular(from_design / "manifest.json", 2 * 1024**2))
            if (from_design / "verification.json").is_file():
                config.update(
                    decode_json(read_regular(from_design / "verification.json", 2 * 1024**2))
                )
            config["design_requirements"] = design.get("requirements", [])
        checks = object_records(config.get("checks", []))
        roles = {
            c.get("role")
            for c in checks
            if c.get("kind", "browser") in {"browser", "visual"} and c.get("required", True)
        }
        if not {"target", "preserve"} <= roles:
            return {
                "status": "blocked",
                "case_id": None,
                "request": request,
                "actions": [
                    {
                        "code": "acceptance_checks_required",
                        "message": (
                            "Define independent target and preserve browser checks in ddk.toml "
                            "or the design verification.json. No hashes are required."
                        ),
                    }
                ],
                "detected": self.detect(),
                "dry_run": dry_run,
            }
        if dry_run:
            return {
                "status": "ready",
                "request": request,
                "checks": checks,
                "scope_paths": config.get("scope_paths", []),
                "git_base": git_base,
                "dry_run": True,
                "execution_approved": False,
                "actions": [],
            }
        if not request or len(request) > 8192:
            raise ValueError("invalid_request")
        snapshot = (
            capture_source(baseline)
            if baseline is not None
            else capture_git_source(self.repository, git_base)
        )
        commit = None if baseline is not None else resolve_git_ref(self.repository, git_base)
        current = (
            capture_source(baseline)
            if baseline is not None
            else capture_git_worktree(self.repository)
        )
        scope = config.get("scope_paths")
        if scope is None:
            before = {f.path: f.sha256 for f in snapshot.files}
            after = {f.path: f.sha256 for f in current.files}
            scope = [p for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]
        scope = string_values(scope)
        if not scope:
            raise ValueError("change_scope_required")
        for path in scope:
            normalize_change_path(path)
        env, binary = (
            observed_environment
            if observed_environment is not None
            else await observe_environment(self.repository)
        )
        env = copy.deepcopy(env)
        validate_record(env)
        payloads: dict[str, bytes] = {f.path: f.content for f in snapshot.files}
        payloads["environment/host.json"] = canonical_json(env)
        payloads["environment/tools.json"] = canonical_json(observe_tools(self.repository))
        compiled: list[Record] = []
        criteria = ["criteria/execution.json"]
        for index, definition in enumerate(checks):
            ident = definition.get("check_id", f"check-{index}")
            if (
                not isinstance(ident, str)
                or not ident
                or any(
                    c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for c in ident
                )
            ):
                raise ValueError("invalid_check_identifier")
            kind = definition.get("kind", "browser")
            path = f"criteria/{ident}.json"
            if kind in {"browser", "visual"}:
                steps: list[Record] = []
                for number, raw in enumerate(object_records(definition.get("steps", []))):
                    selector = raw.get("selector")
                    if isinstance(selector, str):
                        selector = {"strategy": "css", "value": selector, "name": None}
                    steps.append(
                        {
                            "step_id": f"step-{number}",
                            "action": raw["action"],
                            "selector": selector,
                            "value": raw.get("value"),
                            "count": raw.get("count"),
                            "reference_path": raw.get("reference_path"),
                            "rgb_tolerance": raw.get("rgb_tolerance"),
                            "max_mismatch_ppm": raw.get("max_mismatch_ppm"),
                            "timeout_ms": raw.get("timeout_ms", 5000),
                        }
                    )
                flow: Record = {
                    "record_type": "flow",
                    "schema_version": "verified-change/1",
                    "flow_id": ident,
                    "check_id": ident,
                    "entry_path": definition.get("entry_path", "/"),
                    "fixture_sha256": env["fixture_sha256"],
                    "steps": steps,
                }
                validate_record(flow)
                data = canonical_json(flow)
            else:
                data = canonical_json(definition.get("policy", {}) if kind == "policy" else {})
            payloads[path] = data
            criteria.append(path)
            check: Record = {
                "check_id": ident,
                "role": definition["role"],
                "required": definition.get("required", True),
                "kind": kind,
                "definition_path": path,
                "definition_sha256": hashlib.sha256(data).hexdigest(),
                "command_argv": definition.get("command_argv", []),
                "viewport": definition.get("viewport", {"width": 1280, "height": 800})
                if kind in {"browser", "visual"}
                else None,
                "timeout_ms": definition.get("timeout_ms", 30000),
            }
            for key in ("allow_skipped", "report_adapter"):
                if key in definition:
                    check[key] = definition[key]
            compiled.append(check)
        requirements: list[Record] = (
            object_records(config["requirements"])
            if config.get("requirements")
            else [
                {
                    "requirement_id": "REQ-001",
                    "description": request[:2000],
                    "required": True,
                    "check_ids": [c["check_id"] for c in compiled],
                    "allow_delete": config.get("allow_delete", False),
                }
            ]
        )
        for index, requirement in enumerate(object_records(config.get("design_requirements", []))):
            requirement_id = requirement.get(
                "req_id", requirement.get("requirement_id", f"DESIGN-{index}")
            )
            if any(r["requirement_id"] == requirement_id for r in requirements):
                continue
            mapped = requirement.get("check_ids", [])
            if mapped and set(string_values(mapped)) <= {c["check_id"] for c in compiled}:
                description = requirement.get(
                    "description", requirement.get("title", "Design requirement")
                )
                if not isinstance(description, str):
                    raise ValueError("design_requirement_invalid")
                requirements.append(
                    {
                        "requirement_id": requirement_id,
                        "description": description[:2000],
                        "required": True,
                        "check_ids": mapped,
                    }
                )
                continue
            ident = f"design-{index}"
            path = f"criteria/{ident}.json"
            payloads[path] = canonical_json({"review_required": True})
            criteria.append(path)
            compiled.append(
                {
                    "check_id": ident,
                    "role": "policy",
                    "required": True,
                    "kind": "policy",
                    "definition_path": path,
                    "definition_sha256": hashlib.sha256(payloads[path]).hexdigest(),
                    "command_argv": [],
                    "viewport": None,
                    "timeout_ms": 1000,
                }
            )
            description = requirement.get(
                "description", requirement.get("title", "Design acceptance requires review")
            )
            if not isinstance(description, str):
                raise ValueError("design_requirement_invalid")
            requirements.append(
                {
                    "requirement_id": requirement_id,
                    "description": description[:2000],
                    "required": True,
                    "check_ids": [ident],
                }
            )
        plan = {
            "format": "verified-evaluator/1",
            "environment_path": "environment/host.json",
            "criteria_paths": criteria,
            "environment_paths": ["environment/host.json", "environment/tools.json"],
            "preview_argv": config.get("preview_argv", []),
            "frozen_time": config.get("frozen_time", "2026-01-01T00:00:00+00:00"),
            "browser_executable": binary,
            "visual_references": [],
        }
        payloads["criteria/execution.json"] = canonical_json(plan)
        source_names = {f.path for f in snapshot.files}
        if source_names & set(criteria + ["environment/host.json", "environment/tools.json"]):
            raise ValueError("bootstrap_input_collision")
        files = [
            _file(path, data, next((f.mode for f in snapshot.files if f.path == path), 0o644))
            for path, data in payloads.items()
        ]
        inputs = [
            {
                **f.manifest_entry(),
                "role": "source"
                if f.path in source_names
                else "criteria"
                if f.path in criteria
                else "environment",
            }
            for f in files
        ]
        case: Record = {
            "record_type": "case",
            "schema_version": "verified-change/1",
            "case_id": str(uuid4()),
            "legacy_alias": None,
            "supersedes_case_id": supersedes_case_id,
            "created_at": record_time(),
            "request": request,
            "scope_paths": scope,
            "assurance_required": env["assurance"],
            "baseline_tree_sha256": snapshot.tree_sha256,
            "environment_sha256": manifest_digest(
                f for f in files if f.path in {"environment/host.json", "environment/tools.json"}
            ),
            "evaluator_sha256": manifest_digest(f for f in files if f.path in criteria),
            "inputs": inputs,
            "requirements": requirements,
            "checks": compiled,
            "limits": {**DEFAULT_LIMITS, **config.get("limits", {})},
            "source_origin": "design_pkg"
            if from_design
            else "directory"
            if baseline
            else "git_ref",
        }
        if commit:
            case["git_base_ref"] = commit
        store = VerifiedChangeStore(self.repository)
        return store.publish_case(case, payloads)

    def detect(self) -> Record:
        return {
            "manifests": [
                name
                for name in ("pyproject.toml", "package.json", "ddk.toml")
                if (self.repository / name).is_file()
            ],
            "playwright_configs": [p.name for p in self.repository.glob("playwright.config.*")],
            "git": (self.repository / ".git").exists(),
        }

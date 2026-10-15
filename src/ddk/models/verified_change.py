"""The runtime contract for immutable verified-change records."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from functools import lru_cache
from importlib.resources import files
from typing import Any, cast
from urllib.parse import urljoin, urlsplit

from jsonschema import Draft202012Validator, FormatChecker

from ddk.security.repo_paths import ensure_distinct_paths, normalize_source_path

type Record = dict[str, Any]
MAX_RECORD_BYTES = 2 * 1024 * 1024
MAX_RECORD_DEPTH = 32


class ContractError(ValueError):
    """A stored or incoming record violates the approved contract."""


def _inspect(value: object, depth: int = 0) -> None:
    if depth > MAX_RECORD_DEPTH:
        raise ContractError("record_depth_limit")
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if not isinstance(key, str):
                raise ContractError("non_string_json_key")
            _inspect(key, depth + 1)
            _inspect(item, depth + 1)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            _inspect(item, depth + 1)
    elif isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ContractError("invalid_utf8") from error
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError("non_finite_number")
    elif value is not None and not isinstance(value, (int, bool)):
        raise ContractError("non_json_value")


def canonical_json(record: object) -> bytes:
    """Return the fixed UTF-8 representation used by the approved examples."""
    _inspect(record)
    payload = json.dumps(
        record, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(payload) > MAX_RECORD_BYTES:
        raise ContractError("record_size_limit")
    return payload


def record_digest(record: object) -> str:
    return hashlib.sha256(canonical_json(record)).hexdigest()


def object_record(value: object) -> Record:
    """Validate a JSON object at an untrusted nested boundary."""
    _inspect(value)
    if not isinstance(value, dict):
        raise ContractError("record_object_required")
    return cast(Record, value)


def object_records(value: object) -> list[Record]:
    if not isinstance(value, list):
        raise ContractError("record_array_required")
    return [object_record(item) for item in cast(list[object], value)]


def string_values(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ContractError("string_array_required")
    items = cast(list[object], value)
    if any(not isinstance(item, str) for item in items):
        raise ContractError("string_array_required")
    return cast(list[str], items)


def application_changes(case: Record, run: Record, target: Record | None = None) -> list[Record]:
    """Derive the complete target-to-final plan from sealed baseline and run records."""
    baseline = {
        i["path"]: (i["sha256"], i["mode"]) for i in case["inputs"] if i["role"] == "source"
    }
    final = {c["path"]: (c["after_sha256"], c["after_mode"]) for c in run["changes"]}
    previous = (
        {c["path"]: (c["after_sha256"], c["after_mode"]) for c in target["changes"]}
        if target
        else {}
    )
    answer: list[Record] = []
    for path in sorted(set(final) | set(previous)):
        before_hash, before_mode = previous.get(path, baseline.get(path, (None, None)))
        after_hash, after_mode = final.get(path, baseline.get(path, (None, None)))
        action = (
            "unchanged"
            if (before_hash, before_mode) == (after_hash, after_mode)
            else "delete"
            if after_hash is None
            else "create"
            if before_hash is None
            else "update"
        )
        answer.append(
            {
                "path": path,
                "action": action,
                "before_sha256": before_hash,
                "before_mode": before_mode,
                "after_sha256": after_hash,
                "after_mode": after_mode,
            }
        )
    return answer


def _pairs(items: list[tuple[str, Any]]) -> Record:
    result: Record = {}
    for key, value in items:
        if key in result:
            raise ContractError("duplicate_json_key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ContractError("non_finite_number:" + value)


def decode_json(payload: bytes) -> Record:
    """Decode untrusted bytes without accepting ambiguous JSON values."""
    if len(payload) > MAX_RECORD_BYTES:
        raise ContractError("record_size_limit")
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ContractError("invalid_json:" + str(error)) from error
    _inspect(value)
    if not isinstance(value, dict):
        raise ContractError("record_object_required")
    return cast(Record, value)


def _local_references(value: object) -> None:
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            if key in {"$ref", "$dynamicRef"} and (
                not isinstance(item, str) or not item.startswith("#/")
            ):
                raise ContractError("external_schema_reference")
            _local_references(item)
    elif isinstance(value, list):
        for item in cast(list[object], value):
            _local_references(item)


def _date_time(value: object) -> bool:
    if not isinstance(value, str):
        return True
    if (
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value,
        )
        is None
    ):
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


@lru_cache(maxsize=1)
def contract_validator() -> Draft202012Validator:
    packaged = files("ddk").joinpath("assets/verified-change/contract.schema.json")
    payload = packaged.read_bytes()
    schema = decode_json(payload)
    _local_references(schema)
    Draft202012Validator.check_schema(schema)
    checker = FormatChecker()
    checker.checks("date-time")(_date_time)
    return Draft202012Validator(schema, format_checker=checker)


def validate_structure(record: Record) -> None:
    """Validate bounded JSON values and the single approved schema."""
    canonical_json(record)
    _local_references(record)
    iterate = cast(Any, contract_validator()).iter_errors
    errors = sorted(iterate(record), key=lambda e: str(e.path))
    if errors:
        raise ContractError("schema:" + errors[0].message[:240])


def validate_record(
    record: Record, cases: Record | None = None, runs: Record | None = None
) -> None:
    """Validate structure first and then relationships against fixed records."""
    validate_structure(record)
    diagnostics = semantic_errors(record, cases or {}, runs or {})
    if diagnostics:
        raise ContractError(";".join(diagnostics))


def parse_record(payload: bytes, cases: Record | None = None, runs: Record | None = None) -> Record:
    record = decode_json(payload)
    validate_record(record, cases, runs)
    return record


def _path_collisions(paths: list[str]) -> bool:
    try:
        ensure_distinct_paths(paths)
    except ValueError:
        return True
    return False


def safe_path(value: str) -> bool:
    try:
        normalize_source_path(value)
    except ValueError:
        return False
    return ":" not in value


def relative_url(value: str | None) -> bool:
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        return False
    base = urlsplit("http://owned.invalid/")
    parsed = urlsplit(urljoin(base.geturl(), value))
    return (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc)


def semantic_errors(record: Record, cases: Record, runs: Record) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    def unique(values: list[Any], code: str) -> None:
        require(len(values) == len(set(values)), code)

    kind = record["record_type"]
    if kind == "case":
        previous = record["supersedes_case_id"]
        require(
            previous is None or (previous != record["case_id"] and previous in cases),
            "superseded_case_missing_or_self",
        )
        checks = {item["check_id"]: item for item in record["checks"]}
        inputs = {item["path"]: item for item in record["inputs"]}
        unique([item["check_id"] for item in record["checks"]], "duplicate_check")
        unique([item["requirement_id"] for item in record["requirements"]], "duplicate_requirement")
        unique([item["path"] for item in record["inputs"]], "duplicate_input_path")
        require(all(safe_path(path) for path in record["scope_paths"]), "unsafe_scope")
        require(
            all(
                path not in inputs or inputs[path]["role"] == "source"
                for path in record["scope_paths"]
            ),
            "protected_input_in_scope",
        )
        require(all(safe_path(path) for path in inputs), "unsafe_input")
        for requirement in record["requirements"]:
            require(
                set(requirement.get("allowed_paths", record["scope_paths"]))
                <= set(record["scope_paths"]),
                "requirement_scope_mismatch",
            )
            unique(requirement["check_ids"], "duplicate_requirement_link")
            for check_id in requirement["check_ids"]:
                require(check_id in checks, "orphan_check")
                if requirement["required"] and check_id in checks:
                    require(checks[check_id]["required"], "optional_check_for_required_requirement")
        for check in checks.values():
            original = inputs.get(check["definition_path"])
            require(original is not None, "missing_check_definition")
            if original:
                require(original["sha256"] == check["definition_sha256"], "criteria_hash_mismatch")
                require(original["role"] == "criteria", "criteria_role_mismatch")
            if check["kind"] in {"command", "test"}:
                require(bool(check["command_argv"]) and check["viewport"] is None, "command_shape")
            elif check["kind"] in {"browser", "visual"}:
                require(
                    not check["command_argv"] and check["viewport"] is not None, "browser_shape"
                )
        for role in ["target", "preserve"]:
            require(
                any(
                    c["required"] and c["role"] == role and c["kind"] in {"browser", "visual"}
                    for c in checks.values()
                ),
                "missing_independent_" + role,
            )
    elif kind == "run":
        case = cases.get(record["case_id"])
        require(case is not None, "orphan_case")
        if case is None:
            return errors
        from ddk.models.verified_harness import harness_errors

        errors.extend(harness_errors(record, case))
        require(record["case_sha256"] == record_digest(case), "case_hash_mismatch")
        checks = {item["check_id"]: item for item in case["checks"]}
        requirements = {item["requirement_id"] for item in case["requirements"]}
        baseline_inputs = {
            item["path"]: item for item in case["inputs"] if item["role"] == "source"
        }
        artifacts = {item["artifact_id"]: item for item in record["artifacts"]}
        unique([item["artifact_id"] for item in record["artifacts"]], "duplicate_artifact")
        unique([item["path"] for item in record["changes"]], "duplicate_change")
        unique(
            [(item["round_no"], item["phase"], item["check_id"]) for item in record["results"]],
            "duplicate_result",
        )
        unique([item["round_no"] for item in record["rounds"]], "duplicate_round")
        rounds = {item["round_no"]: item for item in record["rounds"]}
        for result in record["results"]:
            require(result["check_id"] in checks, "orphan_result")
            require(result["round_no"] in rounds, "orphan_result_round")
            if result["phase"] == "baseline":
                require(result["round_no"] == 0, "baseline_round_not_zero")
            require(all(item in artifacts for item in result["artifact_ids"]), "orphan_artifact")
        for item in record["artifacts"]:
            require(safe_path(item["path"]), "unsafe_artifact_path")
        for change in record["changes"]:
            require(change["path"] in case["scope_paths"], "outside_change_scope")
            require(
                all(value in requirements for value in change["requirement_ids"]),
                "orphan_change_requirement",
            )
            exists = change["before_sha256"] is not None and change["before_mode"] is not None
            deleting = change["action"] == "delete"
            require(
                exists
                if change["action"] in {"update", "delete"}
                else change["before_sha256"] is None and change["before_mode"] is None,
                "change_before_state",
            )
            baseline = baseline_inputs.get(change["path"])
            if change["action"] in {"update", "delete"}:
                require(
                    baseline is not None
                    and baseline["sha256"] == change["before_sha256"]
                    and baseline["mode"] == change["before_mode"],
                    "before_not_baseline",
                )
            else:
                require(baseline is None, "create_existing_baseline")
            linked = [
                r for r in case["requirements"] if r["requirement_id"] in change["requirement_ids"]
            ]
            require(
                all(change["path"] in r.get("allowed_paths", case["scope_paths"]) for r in linked),
                "outside_requirement_scope",
            )
            if deleting:
                require(
                    bool(linked) and all(r.get("allow_delete", False) for r in linked),
                    "delete_not_approved",
                )
                require(
                    all(
                        change[k] is None
                        for k in ("after_sha256", "after_mode", "after_artifact_id")
                    ),
                    "delete_after_state",
                )
            else:
                require(
                    change["after_mode"] == (change["before_mode"] if exists else 420),
                    "mode_changed" if exists else "new_file_mode",
                )
                artifact = artifacts.get(change["after_artifact_id"])
                require(
                    artifact is not None and artifact["sha256"] == change["after_sha256"],
                    "after_artifact_mismatch",
                )
        if record["operation"] == "verify":
            require(all(item["round_no"] == 0 for item in record["rounds"]), "verify_round")
            require(not record["model_calls"], "verify_called_model")
            require(record["source_run_id"] is None, "verify_has_source_run")
        if record["operation"] == "repair":
            require(record["source_run_id"] is not None, "repair_source_missing")
        if record["source_run_id"] is not None:
            source = runs.get(record["source_run_id"])
            require(
                source is not None and source["case_id"] == record["case_id"], "orphan_source_run"
            )
            if source:
                require(
                    source["status"] == "completed" and source["candidate_tree_sha256"] is not None,
                    "source_run_incomplete",
                )
        unique([item["call_id"] for item in record["model_calls"]], "duplicate_call")
        unique([item["attempt_no"] for item in record["model_calls"]], "duplicate_http_attempt")
        held = 0
        for call in record["model_calls"]:
            price = artifacts.get(call["price_artifact_id"])
            require(price is not None and price["kind"] == "price", "missing_price_artifact")
            require(call["round_no"] in rounds, "orphan_call_round")
            if call["state"] == "settled":
                require(
                    all(
                        call[key] is not None
                        for key in [
                            "calculated_micro_usd",
                            "completed_at",
                            "input_tokens",
                            "output_tokens",
                        ]
                    ),
                    "settlement_missing",
                )
                if (call["calculated_micro_usd"] or 0) > call["reserved_micro_usd"]:
                    require(
                        record["decision"] == "blocked"
                        and any(
                            item["code"] == "cost_reservation_exceeded"
                            for item in record["actions"]
                        ),
                        "settlement_above_reservation",
                    )
                held += call["calculated_micro_usd"] or 0
            else:
                held += call["reserved_micro_usd"]
        if record["decision"] in {"ready", "manual-review"}:
            limits = case["limits"]
            require(
                all(call["state"] == "settled" for call in record["model_calls"]), "cost_unknown"
            )
            require(all(record["integrity"].values()), "integrity_not_complete")
            require(
                record["status"] == "completed" and record["finished_at"] is not None,
                "incomplete_success",
            )
            require(
                record["environment_sha256"] == case["environment_sha256"], "environment_mismatch"
            )
            require(record["evaluator_sha256"] == case["evaluator_sha256"], "evaluator_mismatch")
            if case["assurance_required"] == "isolated":
                require(record["assurance"] == "isolated", "assurance_downgraded")
            require(len(record["model_calls"]) <= limits["max_provider_requests"], "request_limit")
            require(held <= limits["budget_micro_usd"], "cost_reservation_limit")
            require(len(record["changes"]) <= limits["max_changed_files"], "change_limit")
            require(
                sum(a["size_bytes"] for a in record["artifacts"]) <= limits["max_artifact_bytes"],
                "artifact_limit",
            )
            latest = record["latest_round"]
            require(latest is not None and latest in rounds, "latest_round_missing")
            if latest is not None and latest in rounds:
                require(rounds[latest]["finished_at"] is not None, "latest_round_incomplete")
                require(latest <= limits["max_fix_attempts"], "fix_limit")
                require(sorted(rounds) == list(range(latest + 1)), "round_sequence")
                require(
                    rounds[latest]["candidate_tree_sha256"] == record["candidate_tree_sha256"],
                    "candidate_round_mismatch",
                )
                require(
                    rounds[latest]["changes_sha256"] == record_digest(record["changes"]),
                    "changes_round_mismatch",
                )
            result_map = {(r["round_no"], r["phase"], r["check_id"]): r for r in record["results"]}
            for check in checks.values():
                if not check["required"]:
                    continue
                candidate = result_map.get((latest, "candidate", check["check_id"]))
                require(
                    candidate is not None and candidate["status"] == "passed",
                    "required_candidate_not_passed",
                )
                if candidate and check["kind"] in {"browser", "visual", "policy"}:
                    require(
                        candidate["evidence_origin"] == "trusted-observer", "untrusted_observation"
                    )
                    require(bool(candidate["artifact_ids"]), "missing_observation_artifact")
                if candidate and check["kind"] == "test":
                    require(
                        (candidate["executed_count"] or 0) > 0
                        and candidate["failed_count"] == 0
                        and (candidate["skipped_count"] == 0 or check.get("allow_skipped", False)),
                        "zero_or_incomplete_test",
                    )
                if check["role"] == "preserve":
                    baseline = result_map.get((0, "baseline", check["check_id"]))
                    require(
                        baseline is not None and baseline["status"] == "passed",
                        "baseline_preserve_not_passed",
                    )
                    if baseline and check["kind"] in {"browser", "visual"}:
                        require(
                            baseline["evidence_origin"] == "trusted-observer",
                            "untrusted_baseline_observation",
                        )
                        require(bool(baseline["artifact_ids"]), "missing_baseline_artifact")
                    if baseline and check["kind"] == "test":
                        require(
                            (baseline["executed_count"] or 0) > 0
                            and baseline["failed_count"] == 0
                            and (
                                baseline["skipped_count"] == 0 or check.get("allow_skipped", False)
                            ),
                            "baseline_test_not_executed",
                        )
            require(
                record["duration_ms"] is not None
                and record["duration_ms"] <= limits["run_timeout_ms"],
                "run_deadline",
            )
        if record["decision"] == "manual-review":
            require(bool(record["actions"]), "review_without_reason")
            latest = record["latest_round"]
            mapped = {(r["round_no"], r["phase"], r["check_id"]): r for r in record["results"]}
            require(
                all(
                    mapped.get((latest, "candidate", c["check_id"]), {}).get("status") == "passed"
                    for c in checks.values()
                    if c["required"]
                ),
                "blocked_precedes_review",
            )
    elif kind == "apply":
        unique([entry["path"] for entry in record["entries"]], "duplicate_apply_path")
        run = runs.get(record["run_id"])
        require(run is not None, "orphan_apply_run")
        if run:
            require(
                run["status"] == "completed" and run["decision"] == "ready", "apply_run_not_ready"
            )
            require(record["case_id"] == run["case_id"], "apply_case_mismatch")
            require(record["run_sha256"] == record_digest(run), "apply_run_hash")
            require(record["changes_sha256"] == record_digest(run["changes"]), "apply_changes_hash")
            target_id = record.get("target_run_id")
            target = runs.get(target_id) if target_id is not None else None
            if target_id is not None:
                require(
                    target_id in {run["run_id"], run["source_run_id"]}
                    and target is not None
                    and target["case_id"] == run["case_id"],
                    "application_source_not_bound",
                )
            case = cases.get(run["case_id"])
            require(case is not None, "orphan_apply_case")
            if case is None:
                return errors
            changes = {c["path"]: c for c in application_changes(case, run, target)}
            require(
                set(changes) == {e["path"] for e in record["entries"]}, "apply_entries_mismatch"
            )
            for entry in record["entries"]:
                change = changes.get(entry["path"])
                if change:
                    require(
                        all(
                            entry[k] == change[k]
                            for k in ("before_sha256", "before_mode", "after_sha256", "after_mode")
                        ),
                        "apply_entry_state",
                    )
                require(
                    (
                        entry["staged_path"] is None
                        if change and change["after_sha256"] is None
                        else entry["staged_path"] is not None and safe_path(entry["staged_path"])
                    ),
                    "unsafe_staged_path",
                )
                if entry["before_sha256"] is not None:
                    require(
                        entry["backup_path"] is not None and safe_path(entry["backup_path"]),
                        "backup_missing",
                    )
        if record["state"] == "applied":
            require(record["postcheck_at"] is not None, "postcheck_missing")
            require(all(e["state"] == "written" for e in record["entries"]), "applied_entry_state")
        if record["state"] == "rolled_back":
            require(record["postcheck_at"] is not None, "rollback_postcheck_missing")
            require(
                all(e["state"] == "restored" for e in record["entries"]), "restored_entry_state"
            )
        if record["state"] in {"prepared", "conflict"}:
            require(
                all(e["state"] in {"prepared", "conflict"} for e in record["entries"]),
                "unstarted_entry_state",
            )
    elif kind == "flow":
        require(relative_url(record["entry_path"]), "external_entry")
        unique([step["step_id"] for step in record["steps"]], "duplicate_step")
        for step in record["steps"]:
            action = step["action"]
            if action in {"goto", "expect-url"}:
                require(
                    relative_url(step["value"]) and step["selector"] is None,
                    "external_or_invalid_url",
                )
            elif action == "snapshot":
                require(
                    step["reference_path"] is not None and safe_path(step["reference_path"]),
                    "snapshot_reference_missing",
                )
                require(
                    step["rgb_tolerance"] is not None and step["max_mismatch_ppm"] is not None,
                    "snapshot_threshold_missing",
                )
            elif action == "expect-ax-tree":
                require(
                    isinstance(step["value"], str) and bool(step["value"]), "step_value_missing"
                )
            elif action == "expect-no-console-error":
                require(step["selector"] is None, "unused_selector")
            else:
                require(step["selector"] is not None, "selector_missing")
                if action in {"fill", "press", "expect-text"}:
                    require(step["value"] is not None, "step_value_missing")
                if action == "press":
                    require(bool(step["value"]), "empty_press")
                if action == "expect-count":
                    require(step["count"] is not None, "step_count_missing")
            if action not in {
                "goto",
                "expect-url",
                "fill",
                "press",
                "expect-text",
                "expect-ax-tree",
            }:
                require(step["value"] is None, "unused_step_value")
            if action != "expect-count":
                require(step["count"] is None, "unused_step_count")
            if action != "snapshot":
                require(
                    all(
                        step[k] is None
                        for k in ["reference_path", "rgb_tolerance", "max_mismatch_ppm"]
                    ),
                    "unused_snapshot_values",
                )
    elif kind == "environment":
        require(record["endpoint_kind"] == "local", "remote_endpoint")
        if record["assurance"] == "isolated":
            require(
                record["app_image_sha256"] is not None
                and record["checker_image_sha256"] is not None,
                "missing_isolated_images",
            )
    paths: list[str] = []
    if kind == "case":
        paths = [item["path"] for item in record["inputs"]]
        require(not _path_collisions(record["scope_paths"]), "scope_path_collision")
    elif kind == "run":
        paths = [item["path"] for item in record["artifacts"]]
    elif kind == "apply":
        paths = [entry["path"] for entry in record["entries"]]
    require(not _path_collisions(paths), "path_collision")
    return errors

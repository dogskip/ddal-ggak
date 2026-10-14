"""Check design documents and hypothetical records; this is not a product evaluator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY = Path(__file__).resolve().parents[3]
DESIGN = REPOSITORY / "docs/design"
DATA = DESIGN / "verified-change"


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def safe_path(value: str) -> bool:
    parts = value.split("/")
    return (
        bool(value)
        and not value.startswith("/")
        and all(
            part not in {"", ".", "..", ".git", ".ddk"}
            and not part.startswith(".env")
            and "\\" not in part
            and ":" not in part
            and "\0" not in part
            for part in parts
        )
    )


def field_rows(definition: dict) -> list[str]:
    rows = []
    for name, outer in definition.get("properties", {}).items():
        branches = outer.get("anyOf", [outer])
        nullable = any(branch.get("type") == "null" for branch in branches)
        values = [branch for branch in branches if branch.get("type") != "null"]
        if len(values) != 1:
            raise ValueError("unsupported_field_union:" + name)
        value = values[0]

        def type_name(item: dict) -> str:
            if "$ref" in item:
                return item["$ref"].rsplit("/", 1)[-1]
            if "const" in item:
                return "const " + str(item["const"])
            if "enum" in item:
                return "enum " + ", ".join(str(x) for x in item["enum"])
            if item.get("type") == "array":
                return "array<" + type_name(item["items"]) + ">"
            return item["type"]

        description = outer.get("description", value.get("description", ""))
        constraints = []
        for key in [
            "minimum",
            "maximum",
            "minLength",
            "maxLength",
            "pattern",
            "format",
            "minItems",
            "maxItems",
            "uniqueItems",
        ]:
            if key in value:
                constraints.append(f"{key}={value[key]}")
        detail = "; ".join([description] + constraints).strip("; ")
        cells = [
            f"`{name}`",
            type_name(value),
            "허용" if nullable else "불가",
            "없음; 명시 필수",
            detail,
        ]
        rows.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return rows


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


def semantic_errors(record: dict, cases: dict, runs: dict) -> list[str]:
    errors: list[str] = []

    def require(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    def unique(values: list, code: str) -> None:
        require(len(values) == len(set(values)), code)

    kind = record["record_type"]
    if kind == "case":
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
        require(record["case_sha256"] == digest(case), "case_hash_mismatch")
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
            require(
                exists
                if change["action"] == "update"
                else change["before_sha256"] is None and change["before_mode"] is None,
                "change_before_state",
            )
            baseline = baseline_inputs.get(change["path"])
            if change["action"] == "update":
                require(
                    baseline is not None
                    and baseline["sha256"] == change["before_sha256"]
                    and baseline["mode"] == change["before_mode"],
                    "before_not_baseline",
                )
            else:
                require(baseline is None, "create_existing_baseline")
            if exists:
                require(change["after_mode"] == change["before_mode"], "mode_changed")
            else:
                require(change["after_mode"] == 420, "new_file_mode")
            artifact = artifacts.get(change["after_artifact_id"])
            require(
                artifact is not None and artifact["sha256"] == change["after_sha256"],
                "after_artifact_mismatch",
            )
        if record["operation"] == "verify":
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
                    rounds[latest]["changes_sha256"] == digest(record["changes"]),
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
                        and candidate["skipped_count"] == 0,
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
                            and baseline["skipped_count"] == 0,
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
            require(record["run_sha256"] == digest(run), "apply_run_hash")
            require(record["changes_sha256"] == digest(run["changes"]), "apply_changes_hash")
            changes = {c["path"]: c for c in run["changes"]}
            require(
                set(changes) == {e["path"] for e in record["entries"]}, "apply_entries_mismatch"
            )
            for entry in record["entries"]:
                change = changes.get(entry["path"])
                if change:
                    require(
                        all(
                            entry[k] == change[k]
                            for k in ["before_sha256", "after_sha256", "before_mode", "after_mode"]
                        ),
                        "apply_entry_state",
                    )
                require(safe_path(entry["staged_path"]), "unsafe_staged_path")
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
            else:
                require(step["selector"] is not None, "selector_missing")
                if action in {"fill", "press", "expect-text"}:
                    require(step["value"] is not None, "step_value_missing")
                if action == "press":
                    require(bool(step["value"]), "empty_press")
                if action == "expect-count":
                    require(step["count"] is not None, "step_count_missing")
            if action not in {"goto", "expect-url", "fill", "press", "expect-text"}:
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
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    schema = json.loads((DATA / "contract.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    examples = json.loads((DATA / "contract-examples.json").read_text())
    cases = {
        x["record"]["case_id"]: x["record"]
        for x in examples["valid"]
        if x["record"]["record_type"] == "case"
    }
    runs = {
        x["record"]["run_id"]: x["record"]
        for x in examples["valid"]
        if x["record"]["record_type"] == "run"
    }
    failures: list[str] = []
    observations = []
    for group in ["valid", "invalid"]:
        for example in examples[group]:
            record = example["record"]
            schema_errors = sorted(validator.iter_errors(record), key=lambda e: str(e.path))
            errors = ["schema:" + e.message[:160] for e in schema_errors]
            if not errors:
                errors = semantic_errors(record, cases, runs)
            correct = bool(errors) == (group == "invalid")
            if not correct:
                failures.append(example["name"] + ":" + repr(errors))
            observations.append(
                {
                    "name": example["name"],
                    "expected": group,
                    "matched": correct,
                    "diagnostics": errors,
                }
            )
    storage = (DESIGN / "35-verified-change-storage.md").read_text()
    for name, definition in schema["$defs"].items():
        match = re.search(r"^### " + re.escape(name) + r"\n(.*?)(?=^### |\Z)", storage, re.M | re.S)
        rows = re.findall(r"^\| `[^`]+` \|.*$", match.group(1), re.M) if match else []
        if rows != field_rows(definition):
            failures.append("field_table:" + name)
        if any(len(re.findall(r"(?<!\\)\|", row)) != 6 for row in rows):
            failures.append("field_table_columns:" + name)
    analysis = (DESIGN / "reviews/2026-10-14-analysis.md").read_text()
    verification = (DESIGN / "36-verified-change-verification.md").read_text()
    requirements = set(re.findall(r"^\| (VCR-\d+) \|", analysis, re.M))
    traced = set(re.findall(r"^\| (VCR-\d+) \|", verification, re.M))
    if requirements != traced or len(requirements) != 20:
        failures.append("requirement_trace")
    acceptance = set(re.findall(r"^\| (VCT-\d+) \|", verification, re.M))
    if len(acceptance) != 30:
        failures.append("acceptance_trace")
    links = 0
    docs = [
        DESIGN / f"{n}-verified-change-{suffix}.md"
        for n, suffix in [(34, "design"), (35, "storage"), (36, "verification")]
    ]
    docs += sorted((DESIGN / "reviews").glob("2026-10-14-*.md"))
    for doc in docs:
        for target in re.findall(r"\]\(([^)]+)\)", doc.read_text()):
            target = target.strip("<>").split("#", 1)[0]
            if not target or re.match(r"^[a-z]+://", target):
                continue
            links += 1
            if not (doc.parent / target).resolve().exists():
                failures.append("broken_link:" + str(doc.relative_to(REPOSITORY)) + ":" + target)
    refs = re.findall(r'"\$ref":\s*"([^"]+)"', json.dumps(schema))
    for value in refs:
        if not value.startswith("#/$defs/") or value.split("/")[-1] not in schema["$defs"]:
            failures.append("schema_reference:" + value)
    report = {
        "scope": "document schema, hypothetical relations, field tables, traceability, local links",
        "result": "passed" if not failures else "failed",
        "definitions": len(schema["$defs"]),
        "fields": sum(len(d.get("properties", {})) for d in schema["$defs"].values()),
        "valid_examples": len(examples["valid"]),
        "invalid_examples": len(examples["invalid"]),
        "examples_matched": sum(x["matched"] for x in observations),
        "requirements_traced": len(requirements),
        "acceptance_tests_defined": len(acceptance),
        "local_links_checked": links,
        "failures": failures,
        "observations": observations,
        "implementation_evidence": 0,
        "product_effect_evidence": 0,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "observations"}, ensure_ascii=False))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())

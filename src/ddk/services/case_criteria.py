"""Compile acceptance suggestions through the same contracts used for sealed cases."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from ddk.models.verified_change import (
    Record,
    canonical_json,
    contract_validator,
    object_records,
    validate_record,
)
from ddk.models.verified_commands import command_arguments


def compile_checks(config: Record, fixture_sha256: str) -> tuple[list[Record], dict[str, bytes]]:
    command_arguments(config.get("preview_argv", []), allow_empty=True)
    checks = object_records(config.get("checks", []))
    compiled: list[Record] = []
    payloads: dict[str, bytes] = {}
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
                "fixture_sha256": fixture_sha256,
                "steps": steps,
            }
            validate_record(flow)
            data = canonical_json(flow)
        else:
            data = canonical_json(definition.get("policy", {}) if kind == "policy" else {})
        payloads[path] = data
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
        validator = contract_validator()
        schema = cast(Record, validator.schema)
        errors = list(cast(Any, validator).descend(check, schema["$defs"]["Check"]))
        if errors:
            raise ValueError("invalid_check_definition:" + str(errors[0].message)[:160])
        argv = command_arguments(check["command_argv"], allow_empty=kind not in {"command", "test"})
        if kind in {"command", "test"}:
            if check["viewport"] is not None:
                raise ValueError("command_shape")
        elif argv:
            raise ValueError("browser_or_policy_shape")
        if any(c["check_id"] == ident for c in compiled):
            raise ValueError("duplicate_check_id")
        compiled.append(check)
    return compiled, payloads

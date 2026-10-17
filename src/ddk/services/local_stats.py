"""Read-only cost aggregates; recorded observations never settle a provider invoice."""

from __future__ import annotations

import json
import os
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import cast

from ddk.models.verified_change import MAX_RECORD_BYTES, Record
from ddk.security.file_access import parent_descriptor, read_regular
from ddk.services.verified_budget import audit_run_costs
from ddk.services.verified_change_store import VerifiedChangeStore

MAX_RECORDS = 10_000
_MAX_INTEGER = 2**53 - 1
_MAX_METADATA_BYTES = 64 * 1024**2


def _directories(path: Path, pattern: str) -> list[str]:
    try:
        with (
            parent_descriptor(path / "record") as (descriptor, _),
            os.scandir(descriptor) as entries,
        ):
            names: list[str] = []
            for entry in entries:
                if len(names) >= MAX_RECORDS:
                    raise ValueError("stats_record_limit")
                if entry.name.startswith("."):
                    continue
                if not re.fullmatch(pattern, entry.name) or not entry.is_dir(follow_symlinks=False):
                    raise ValueError("invalid_record_directory")
                names.append(entry.name)
    except FileNotFoundError:
        return []
    return sorted(names)


def _count(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or not 0 <= value <= _MAX_INTEGER:
        raise ValueError("invalid_observed_count")
    return value


def _legacy_cost(value: object) -> int | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        raise ValueError("invalid_recorded_cost")
    try:
        amount = Decimal(str(value)) * 1_000_000
        if not amount.is_finite() or not 0 <= amount <= _MAX_INTEGER:
            raise ValueError("invalid_recorded_cost")
        return int(amount.to_integral_value(rounding=ROUND_HALF_UP))
    except InvalidOperation as error:
        raise ValueError("invalid_recorded_cost") from error


def summarize_costs(repository: Path) -> Record:
    """Aggregate allowlisted numbers from bounded, validated local records."""
    repository = repository.resolve()
    store = VerifiedChangeStore(repository, create=False)
    legacy = _directories(repository / ".ddk/cases", r"C-[0-9]+")
    runs = _directories(store.base_path / "runs", r"[0-9a-f-]{36}")
    if len(legacy) + len(runs) > MAX_RECORDS:
        raise ValueError("stats_record_limit")
    metadata_bytes = 0
    known = reserved = unknown = missing = pending = 0
    inputs = outputs = 0
    input_complete = output_complete = True
    seen: dict[tuple[str, str], tuple[int | None, int | None, int | None, int]] = {}

    def add(
        key: tuple[str, str],
        cost: int | None,
        tokens_in: object,
        tokens_out: object,
        reservation: int = 0,
    ) -> None:
        nonlocal known, reserved, unknown, inputs, outputs, input_complete, output_complete
        observed_in, observed_out = _count(tokens_in), _count(tokens_out)
        observation = (cost, observed_in, observed_out, reservation)
        if key in seen:
            raise ValueError("duplicate_cost_observation")
        seen[key] = observation
        known += cost or 0
        reserved += reservation
        unknown += int(cost is None)
        inputs += observed_in or 0
        outputs += observed_out or 0
        input_complete &= observed_in is not None
        output_complete &= observed_out is not None

    def read(path: Path) -> bytes:
        nonlocal metadata_bytes
        payload = read_regular(path, MAX_RECORD_BYTES)
        metadata_bytes += len(payload)
        if metadata_bytes > _MAX_METADATA_BYTES:
            raise ValueError("stats_metadata_limit")
        return payload

    for case_id in legacy:
        try:
            value = cast(
                object,
                json.loads(read(repository / ".ddk/cases" / case_id / "reports/llm-calls.json")),
            )
        except FileNotFoundError:
            missing += 1
            continue
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in cast(list[object], value)
        ):
            raise ValueError("invalid_legacy_calls")
        for call in cast(list[Record], value):
            sequence = _count(call.get("sequence"))
            status = call.get("status")
            if sequence is None or not isinstance(status, str) or status not in {"ok", "error"}:
                raise ValueError("invalid_legacy_call")
            cost = _legacy_cost(call.get("cost_usd"))
            add(
                (case_id, str(sequence)),
                cost if call["status"] == "ok" else None,
                call.get("input_tokens"),
                call.get("output_tokens"),
            )

    for run_id in runs:
        directory = store.path_for("run", run_id)
        try:
            read(directory / "run.json")
        except FileNotFoundError:
            read(directory / ".pending/run.json")
            pending += 1
        record = store.status(run_id)
        audit_run_costs(store, record)
        for call in record["model_calls"]:
            reservation = _count(call["reserved_micro_usd"])
            assert reservation is not None
            cost = _count(call["calculated_micro_usd"]) if call["state"] == "settled" else None
            add(
                ("verified", call["call_id"]),
                cost,
                call["input_tokens"],
                call["output_tokens"],
                reservation,
            )
    if any(value > _MAX_INTEGER for value in (known, reserved, inputs, outputs)):
        raise ValueError("stats_sum_limit")
    complete = unknown == missing == 0
    return {
        "format": "ddk-local-stats/1",
        "local_only": True,
        "legacy_cases": len(legacy),
        "verified_runs": len(runs),
        "pending_runs": pending,
        "calls": len(seen),
        "unknown_calls": unknown,
        "missing_case_records": missing,
        "known_cost_micro_usd": known,
        "reserved_micro_usd": reserved,
        "recorded_total_micro_usd": known if complete else None,
        "input_tokens": inputs if input_complete and missing == 0 else None,
        "output_tokens": outputs if output_complete and missing == 0 else None,
        "complete": complete,
    }

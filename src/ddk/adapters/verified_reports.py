"""Shared command reports for host and isolated execution."""

from __future__ import annotations

from ddk.adapters.build_runner import BuildResult
from ddk.models.verified_change import Record, decode_json
from ddk.services.verified_change_engine import EvaluationRequest


def check_result(request: EvaluationRequest, check: Record, reason: str | None = None) -> Record:
    return {
        "check_id": check["check_id"],
        "phase": request.phase,
        "status": "unavailable",
        "exit_code": None,
        "executed_count": None,
        "failed_count": None,
        "skipped_count": None,
        "retry_count": 0,
        "duration_ms": 0,
        "reason_code": reason,
        "artifact_ids": [],
        "evidence_origin": "project-report"
        if check["kind"] in {"command", "test"}
        else "trusted-observer",
        "round_no": 0,
    }


def command_report(request: EvaluationRequest, check: Record, answer: BuildResult) -> Record:
    result = check_result(request, check)
    result.update(
        exit_code=answer.returncode,
        status="passed" if answer.success else "failed",
        reason_code=None if answer.success else "command_failed",
    )
    if answer.returncode in {124, 125, 126, 127}:
        result.update(status="unavailable", reason_code="command_unavailable")
    elif check["kind"] == "test":
        try:
            counts = decode_json(answer.stdout.encode())
            keys = {"executed_count", "failed_count", "skipped_count"}
            if not (
                set(counts) == keys
                and all(type(counts[key]) is int and 0 <= counts[key] <= 2**53 - 1 for key in keys)
                and counts["failed_count"] <= counts["executed_count"]
            ):
                raise ValueError("test_report_invalid")
            result.update(counts)
            if counts["executed_count"] == 0 or counts["skipped_count"]:
                result.update(status="unavailable", reason_code="test_report_incomplete")
            elif counts["failed_count"]:
                result.update(status="failed", reason_code="test_failed")
        except ValueError:
            result.update(status="unavailable", reason_code="test_report_invalid")
    return result

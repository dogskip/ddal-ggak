"""Shared command reports for host and isolated execution."""

from __future__ import annotations

from xml.etree import ElementTree

from ddk.adapters.build_runner import BuildResult
from ddk.models.verified_change import Record, decode_json, object_record
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


def _count(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**53 - 1:
        raise ValueError("test_report_invalid")
    return value


def normalize_report(payload: bytes, adapter: str = "ddk-json") -> Record:
    if len(payload) > 2 * 1024**2:
        raise ValueError("test_report_invalid")
    if adapter == "junit-xml":
        payload.decode("utf-8", errors="strict")
        if b"\x00" in payload or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise ValueError("test_report_invalid")
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as error:
            raise ValueError("test_report_invalid") from error
        if root.tag not in {"testsuite", "testsuites"}:
            raise ValueError("test_report_invalid")
        tests = list(root.iter("testcase"))
        if not tests:
            raise ValueError("test_report_invalid")
        skipped = sum(t.find("skipped") is not None for t in tests)
        failed = sum(t.find("failure") is not None or t.find("error") is not None for t in tests)
        executed = len(tests) - skipped
        if any(
            t.find("skipped") is not None
            and (t.find("error") is not None or t.find("failure") is not None)
            for t in tests
        ):
            raise ValueError("test_report_invalid")
        for suite in root.iter():
            if suite.tag not in {"testsuite", "testsuites"}:
                continue
            children = list(suite.iter("testcase"))
            observed = {
                "tests": len(children),
                "failures": sum(t.find("failure") is not None for t in children),
                "errors": sum(t.find("error") is not None for t in children),
                "skipped": sum(t.find("skipped") is not None for t in children),
            }
            for name, actual in observed.items():
                if name in suite.attrib and int(suite.attrib[name]) != actual:
                    raise ValueError("test_report_invalid")

    else:
        report = decode_json(payload)
        if adapter == "ddk-json":
            if set(report) != {"executed_count", "failed_count", "skipped_count"}:
                raise ValueError("test_report_invalid")
            executed, failed, skipped = (
                _count(report[k]) for k in ("executed_count", "failed_count", "skipped_count")
            )
        elif adapter in {"jest-json", "vitest-json"}:
            total = _count(report["numTotalTests"])
            failed = _count(report["numFailedTests"])
            skipped = _count(report["numPendingTests"]) + _count(report.get("numTodoTests", 0))
            executed = total - skipped
            if "numPassedTests" in report and _count(report["numPassedTests"]) + failed != executed:
                raise ValueError("test_report_invalid")
            if _count(report.get("numRuntimeErrorTestSuites", 0)):
                raise ValueError("test_report_invalid")
        elif adapter == "pytest-json":
            summary = object_record(report["summary"])
            total = _count(summary["total"])
            skipped = _count(summary.get("skipped", 0)) + _count(summary.get("xfailed", 0))
            failed = (
                _count(summary.get("failed", 0))
                + _count(summary.get("error", 0))
                + _count(summary.get("xpassed", 0))
            )
            executed = total - skipped
            if _count(summary.get("passed", 0)) + failed != executed:
                raise ValueError("test_report_invalid")
        elif adapter == "playwright-json":
            stats = object_record(report["stats"])
            if report.get("errors"):
                raise ValueError("test_report_invalid")
            failed = _count(stats["unexpected"]) + _count(stats.get("flaky", 0))
            skipped = _count(stats["skipped"])
            executed = _count(stats["expected"]) + failed
        else:
            raise ValueError("test_report_invalid")
    if not 0 <= failed <= executed or skipped < 0:
        raise ValueError("test_report_invalid")
    return {"executed_count": executed, "failed_count": failed, "skipped_count": skipped}


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
            counts = normalize_report(
                answer.stdout.encode(), check.get("report_adapter", "ddk-json")
            )
            result.update(counts)
            if counts["executed_count"] == 0 or (
                counts["skipped_count"] and not check.get("allow_skipped", False)
            ):
                result.update(status="unavailable", reason_code="test_report_incomplete")
            elif counts["failed_count"]:
                result.update(status="failed", reason_code="test_failed")
        except (ValueError, KeyError, TypeError, OverflowError):
            result.update(status="unavailable", reason_code="test_report_invalid")
    return result

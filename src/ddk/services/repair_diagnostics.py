"""Shared failure signatures and conservative progress control without model judgments."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from xml.etree import ElementTree

from ddk.models.verified_change import Record, record_digest
from ddk.security.redact import redact_string
from ddk.services.verified_change_engine import EvaluationOutcome

_OWNED_PATH = re.compile(
    r"(?:/private)?/var/folders/[^\s\"']+/T/ddk-[^/\s\"']+|/tmp/ddk-[^/\s\"']+"
)
_PYTEST_TIME = re.compile(
    r"^(?P<summary>[= ]*\d+ (?:failed|passed|errors?|skipped|xfailed|xpassed|deselected|warnings?)"
    r"(?:, \d+ (?:failed|passed|errors?|skipped|xfailed|xpassed|deselected|warnings?))*)"
    r" in \d+(?:\.\d+)?s(?: \([^\n]*\))?(?P<ending>[= ]*)$",
    re.MULTILINE,
)


def _stable_diagnostic(text: str) -> str:
    text = _PYTEST_TIME.sub(r"\g<summary> in <duration>s\g<ending>", text)
    prefix, marker, report = text.partition("\nREPORT:\n")
    if marker and report.lstrip().startswith("<") and "<!" not in report:
        try:
            root = ElementTree.fromstring(report)
        except ElementTree.ParseError:
            return text
        if root.tag in {"testsuite", "testsuites"}:
            for node in root.iter():
                if node.tag in {"testsuite", "testsuites", "testcase"}:
                    for key in ("time", "timestamp", "hostname"):
                        node.attrib.pop(key, None)
            return prefix + marker + ElementTree.tostring(root, encoding="unicode")
    return text


def error_signature(
    check_id: str, reason_code: str, diagnostics: Iterable[tuple[str, bytes]]
) -> str:
    values: list[Record] = []
    for kind, raw in diagnostics:
        try:
            text = redact_string(raw.decode("utf-8", errors="strict")).replace("\r\n", "\n")
            text = _OWNED_PATH.sub("<ddk-workspace>", text)
            text = _stable_diagnostic(text)
        except UnicodeError:
            text = "binary-sha256:" + hashlib.sha256(raw).hexdigest()
        values.append({"kind": kind, "content": text})
    return record_digest({"check_id": check_id, "reason_code": reason_code, "diagnostics": values})


def failure_state(
    outcome: EvaluationOutcome, required_ids: set[str] | None = None
) -> tuple[Record, ...]:
    artifacts = {a.artifact_id: a for a in outcome.artifacts}
    return tuple(
        {
            "check_id": result["check_id"],
            "reason_code": result["reason_code"] or "check_failed",
            "error_signature_sha256": error_signature(
                result["check_id"],
                result["reason_code"] or "check_failed",
                (
                    (artifacts[key].kind, artifacts[key].content)
                    for key in result["artifact_ids"]
                    if key in artifacts
                    and artifacts[key].kind in {"log", "trace", "data", "ax_snapshot"}
                ),
            ),
        }
        for result in sorted(outcome.results, key=lambda row: str(row["check_id"]))
        if result["status"] == "failed"
        and (required_ids is None or result["check_id"] in required_ids)
    )


class RepairStallTracker:
    def __init__(self) -> None:
        self._previous: tuple[tuple[str, str, str], ...] = ()
        self._streak = 1

    def observe(self, failures: tuple[Record, ...], round_no: int) -> Record | None:
        current = tuple(
            sorted((r["check_id"], r["reason_code"], r["error_signature_sha256"]) for r in failures)
        )
        previous = self._previous
        self._previous = current
        if not previous or not current:
            self._streak = 1
            return None
        identical = current == previous
        self._streak = self._streak + 1 if identical else 1
        if not identical and len(current) < len(previous):
            return None
        return {
            "round_no": round_no,
            "stall_category": "identical_error_signature"
            if identical
            else "failed_count_non_decreasing",
            "repeated_signature_sha256": record_digest([list(row) for row in current]),
            "streak_count": self._streak if identical else 2,
            "action_taken": "halt_repair_stalled"
            if self._streak >= 3
            else "inject_anti_oscillation_constraint",
        }

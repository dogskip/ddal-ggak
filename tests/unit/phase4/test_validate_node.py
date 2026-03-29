"""Tests for validate_node — Wave 4 TDD (VALID-01/02/03)."""
from __future__ import annotations

from unittest.mock import MagicMock

from ddk.graph.nodes.validate import validate_node
from ddk.models.validation import RuntimeValidationReport


class FakeRuntimeValidator:
    def __init__(self, report: RuntimeValidationReport, vis_report=None):
        self.report = report
        self.vis_report = vis_report

    async def run(self, state, **kwargs):
        return self.report, self.vis_report


def make_passing_report(case_id: str = "tc") -> RuntimeValidationReport:
    return RuntimeValidationReport(
        case_id=case_id, build_success=True, type_check_success=True, lint_success=True
    )


async def test_validate_node_writes_report_to_state() -> None:
    report = make_passing_report()
    container = MagicMock()
    container.runtime_validator = FakeRuntimeValidator(report)
    state: dict = {"case_id": "tc", "failure_hash_history": []}
    result = await validate_node(state, context=container)
    assert result["runtime_validation_report"] == report


async def test_validate_node_does_not_modify_failure_hash_history() -> None:
    """validate_node must NOT touch failure_hash_history — that's autofix_node's job.

    If validate_node appended the hash, route_after_validate would see it immediately
    and return 'exhausted' on the very first cycle — the autofix loop would never run.
    """
    report = make_passing_report()
    container = MagicMock()
    container.runtime_validator = FakeRuntimeValidator(report)
    state: dict = {"case_id": "tc", "failure_hash_history": []}
    result = await validate_node(state, context=container)
    assert "failure_hash_history" not in result, (
        "validate_node must not modify failure_hash_history — "
        "oscillation state belongs to autofix_node"
    )


async def test_validate_node_none_runtime_validator_returns_manual_review() -> None:
    container = MagicMock()
    container.runtime_validator = None
    state: dict = {"case_id": "tc", "failure_hash_history": []}
    result = await validate_node(state, context=container)
    assert result["terminal_state"] == "manual-review-required"

"""Tests for validate_node — Wave 4 TDD (VALID-01/02/03)."""

from __future__ import annotations

from unittest.mock import MagicMock

from ddk.graph.nodes.validate import validate_node
from ddk.models.validation import FailureRecord, RuntimeValidationReport, ValidationStep


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


async def test_validate_node_stops_the_loop_when_the_toolchain_is_missing() -> None:
    """A missing toolchain is not something auto-fix can repair: go straight to manual review."""
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=False,
        lint_success=False,
        steps=[
            ValidationStep(
                name="build",
                status="unavailable",
                summary="dependencies are not installed; run `npm ci` or pass --install",
            )
        ],
    )
    container = MagicMock()
    container.runtime_validator = FakeRuntimeValidator(report)

    result = await validate_node({"case_id": "tc", "failure_hash_history": []}, context=container)

    assert result["terminal_state"] == "manual-review-required"
    assert "dependencies are not installed" in result["error_message"]
    assert result["runtime_validation_report"] == report


async def test_validate_node_keeps_repairing_when_only_the_visual_step_is_unavailable() -> None:
    """Code failures can still be fixed even though the browser check cannot run."""
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=True,
        type_check_success=True,
        lint_success=False,
        failures=[
            FailureRecord(id="f1", taxonomy_id="FT-LINT-001", severity="minor", message="unused")
        ],
        steps=[
            ValidationStep(name="lint", status="failed", summary="1 error(s)"),
            ValidationStep(name="visual", status="unavailable", summary="Chromium is missing"),
        ],
    )
    container = MagicMock()
    container.runtime_validator = FakeRuntimeValidator(report)

    result = await validate_node({"case_id": "tc", "failure_hash_history": []}, context=container)

    assert "terminal_state" not in result
    assert result["runtime_validation_report"] == report


async def test_validate_node_stops_when_only_the_visual_step_is_unavailable_and_code_is_clean() -> (
    None
):
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=True,
        type_check_success=True,
        lint_success=True,
        steps=[
            ValidationStep(name="build", status="passed"),
            ValidationStep(name="visual", status="unavailable", summary="Chromium is missing"),
        ],
    )
    container = MagicMock()
    container.runtime_validator = FakeRuntimeValidator(report)

    result = await validate_node({"case_id": "tc", "failure_hash_history": []}, context=container)

    assert result["terminal_state"] == "manual-review-required"
    assert "visual: Chromium is missing" in result["error_message"]

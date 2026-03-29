"""Tests for ReleaseGate."""

from __future__ import annotations

from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.services.release_gate import ReleaseGate


def _scorecard(overall: float, grade: str = "A") -> Scorecard:
    return Scorecard(
        case_id="C-001",
        precision=overall,
        maintainability=overall,
        automation=overall,
        scalability=overall,
        overall=overall,
        grade=grade,
    )


def test_decide_ready_when_no_blockers_and_high_score() -> None:
    decision = ReleaseGate().decide(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
            ),
            "terminal_state": None,
        },
        _scorecard(0.95, "A"),
    )

    assert decision.decision == "ready"
    assert decision.blockers == []
    assert decision.approved_at is not None


def test_decide_blocked_when_critical_failure_exists() -> None:
    decision = ReleaseGate().decide(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=False,
                type_check_success=True,
                lint_success=True,
                failures=[
                    FailureRecord(
                        id="f-1",
                        taxonomy_id="FT-BUILD-001",
                        severity="critical",
                        message="Build failed",
                    )
                ],
            ),
            "terminal_state": None,
        },
        _scorecard(0.92, "A"),
    )

    assert decision.decision == "blocked"
    assert len(decision.blockers) == 1
    assert decision.blockers[0].severity == "critical"


def test_decide_manual_review_when_terminal_state_requires_it() -> None:
    decision = ReleaseGate().decide(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
            ),
            "terminal_state": "manual-review-required",
        },
        _scorecard(0.84, "B"),
    )

    assert decision.decision == "manual-review"
    assert decision.approved_at is None

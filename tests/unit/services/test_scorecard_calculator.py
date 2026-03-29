"""Tests for ScorecardCalculator."""

from __future__ import annotations

from ddk.models.fix import FixAttempt
from ddk.models.normalization import NormalizationReport
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport
from ddk.services.scorecard_calculator import ScorecardCalculator


def test_calculate_ready_case_returns_high_score() -> None:
    scorecard = ScorecardCalculator().calculate(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
            ),
            "normalization_report": NormalizationReport(case_id="C-001"),
            "visual_regression_report": VisualRegressionReport(
                case_id="C-001",
                reference_path="ref.png",
                generated_path="gen.png",
                ssim_score=0.99,
                threshold=0.92,
                pass_result=True,
            ),
            "fix_attempts": [],
            "retry_budget_remaining": 3,
            "terminal_state": None,
        }
    )

    assert scorecard.overall >= 0.95
    assert scorecard.grade == "A"


def test_calculate_failure_case_reduces_score() -> None:
    scorecard = ScorecardCalculator().calculate(
        {
            "case_id": "C-002",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-002",
                build_success=False,
                type_check_success=False,
                lint_success=True,
                failures=[
                    FailureRecord(
                        id="f-1",
                        taxonomy_id="FT-BUILD-001",
                        severity="critical",
                        message="Build failed",
                    )
                ],
                duration_ms=90_000,
            ),
            "normalization_report": NormalizationReport(
                case_id="C-002",
                drift_score_after=4.0,
            ),
            "visual_regression_report": VisualRegressionReport(
                case_id="C-002",
                reference_path="ref.png",
                generated_path="gen.png",
                ssim_score=0.70,
                threshold=0.92,
                pass_result=False,
            ),
            "fix_attempts": [
                FixAttempt(
                    attempt_number=1,
                    case_id="C-002",
                    trigger_failures=["f-1"],
                    rule_id="R-01",
                    files_patched=["src/App.tsx"],
                    patch_description="attempted fix",
                    success=False,
                )
            ],
            "retry_budget_remaining": 1,
            "terminal_state": "manual-review-required",
        }
    )

    assert scorecard.overall < 0.60
    assert scorecard.grade in {"D", "F"}

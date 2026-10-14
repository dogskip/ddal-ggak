"""Tests for ReleaseGate."""

from __future__ import annotations

from types import SimpleNamespace

from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport, ValidationStep
from ddk.models.visual import VisualRegressionReport
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


def test_image_case_is_blocked_when_visual_evidence_is_missing() -> None:
    decision = ReleaseGate().decide(
        {
            "case_id": "C-visual",
            "case_input": SimpleNamespace(image_paths=["reference.png"]),
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-visual",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
            ),
            "visual_regression_report": None,
            "terminal_state": None,
        },
        _scorecard(0.95, "A"),
    )

    assert decision.decision == "blocked"
    assert "missing-visual-evidence" in {blocker.id for blocker in decision.blockers}


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


def _report_with_steps(*steps: ValidationStep) -> RuntimeValidationReport:
    return RuntimeValidationReport(
        case_id="C-001",
        build_success=True,
        type_check_success=True,
        lint_success=True,
        steps=list(steps),
    )


def test_blocked_when_no_step_could_verify_anything() -> None:
    report = _report_with_steps(
        ValidationStep(name="build", status="skipped", summary="no build script in package.json"),
        ValidationStep(name="typecheck", status="skipped", summary="no tsconfig.json"),
        ValidationStep(name="lint", status="skipped", summary="no ESLint configuration found"),
    )

    decision = ReleaseGate().decide(
        {"case_id": "C-001", "runtime_validation_report": report}, _scorecard(0.95, "A")
    )

    assert decision.decision == "blocked"
    assert "nothing-verified" in {blocker.id for blocker in decision.blockers}


def test_one_passing_step_is_enough_evidence_even_when_others_are_skipped() -> None:
    report = _report_with_steps(
        ValidationStep(name="build", status="passed"),
        ValidationStep(name="lint", status="skipped", summary="no ESLint configuration found"),
    )

    decision = ReleaseGate().decide(
        {"case_id": "C-001", "runtime_validation_report": report}, _scorecard(0.95, "A")
    )

    assert decision.decision == "ready"


def test_missing_toolchain_is_reported_as_its_own_blocker() -> None:
    report = RuntimeValidationReport(
        case_id="C-001",
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

    decision = ReleaseGate().decide(
        {"case_id": "C-001", "runtime_validation_report": report}, _scorecard(0.3, "F")
    )

    assert decision.decision == "blocked"
    environment = next(b for b in decision.blockers if b.id == "validation-environment")
    assert "npm ci" in environment.description


def test_report_without_step_records_keeps_the_old_behaviour() -> None:
    decision = ReleaseGate().decide(
        {"case_id": "C-001", "runtime_validation_report": _report_with_steps()},
        _scorecard(0.95, "A"),
    )

    assert decision.decision == "ready"


def _image_case_state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "case_id": "C-v",
        "case_input": SimpleNamespace(image_paths=["design.png"], visual_check=True),
        "runtime_validation_report": RuntimeValidationReport(
            case_id="C-v",
            build_success=True,
            type_check_success=True,
            lint_success=True,
            failures=[],
        ),
        "visual_regression_report": None,
        "terminal_state": None,
    }
    state.update(overrides)
    return state


def _failed_visual() -> VisualRegressionReport:
    return VisualRegressionReport(
        case_id="C-v",
        reference_path="design.png",
        generated_path="generated.png",
        ssim_score=0.6,
        threshold=0.92,
        pass_result=False,
    )


def test_waived_visual_check_does_not_demand_screenshot_evidence() -> None:
    state = _image_case_state(
        case_input=SimpleNamespace(image_paths=["design.png"], visual_check=False)
    )

    decision = ReleaseGate().decide(state, _scorecard(0.95, "A"))

    assert decision.decision == "ready"
    assert decision.blockers == []


def test_visual_mismatch_and_its_failure_record_make_a_single_blocker() -> None:
    visual_failure = FailureRecord(
        id="v1",
        taxonomy_id="FT-VISUAL-001",
        severity="major",
        message="Rendered page does not match the design: SSIM 0.60 < 0.92",
        source="visual",
    )
    state = _image_case_state(
        visual_regression_report=_failed_visual(),
        runtime_validation_report=RuntimeValidationReport(
            case_id="C-v",
            build_success=True,
            type_check_success=True,
            lint_success=True,
            failures=[visual_failure],
        ),
    )

    decision = ReleaseGate().decide(state, _scorecard(0.95, "A"))

    visual_blockers = [b for b in decision.blockers if b.category == "visual"]
    assert decision.decision == "blocked"
    assert len(visual_blockers) == 1


def test_visual_mismatch_without_a_failure_record_still_blocks() -> None:
    decision = ReleaseGate().decide(
        _image_case_state(visual_regression_report=_failed_visual()), _scorecard(0.95, "A")
    )

    assert [b.id for b in decision.blockers] == ["C-v-visual"]

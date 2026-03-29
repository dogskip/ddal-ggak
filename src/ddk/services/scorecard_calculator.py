"""Deterministic scorecard calculation for Phase 5 certification."""

from __future__ import annotations

from typing import Any, Literal, cast

from ddk.models.fix import FixAttempt
from ddk.models.normalization import NormalizationReport
from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport


def _clamp(value: float) -> float:
    """Clamp a floating-point score into the inclusive [0.0, 1.0] range."""
    return max(0.0, min(1.0, round(value, 2)))


class ScorecardCalculator:
    """Compute a deterministic scorecard from pipeline state."""

    Grade = Literal["A", "B", "C", "D", "F"]

    def calculate(self, state: dict[str, Any]) -> Scorecard:
        """Calculate certification scores from the current graph state."""
        case_id = str(state["case_id"])
        runtime = cast(RuntimeValidationReport | None, state.get("runtime_validation_report"))
        visual = cast(VisualRegressionReport | None, state.get("visual_regression_report"))
        normalization = cast(NormalizationReport | None, state.get("normalization_report"))
        fix_attempts = cast(list[FixAttempt], state.get("fix_attempts", []))

        failures = runtime.failures if runtime is not None else []
        precision = self._precision(runtime, visual, failures)
        maintainability = self._maintainability(normalization, fix_attempts)
        automation = self._automation(state, failures)
        scalability = self._scalability(runtime, visual, fix_attempts, failures)
        overall = _clamp((precision + maintainability + automation + scalability) / 4.0)

        return Scorecard(
            case_id=case_id,
            precision=precision,
            maintainability=maintainability,
            automation=automation,
            scalability=scalability,
            overall=overall,
            grade=self._grade(overall),
            details={
                "failure_count": str(len(failures)),
                "fix_attempts": str(len(fix_attempts)),
                "terminal_state": str(state.get("terminal_state")),
            },
        )

    def _precision(
        self,
        runtime: RuntimeValidationReport | None,
        visual: VisualRegressionReport | None,
        failures: list[FailureRecord],
    ) -> float:
        score = 1.0

        for failure in failures:
            if failure.severity == "critical":
                score -= 0.40
            elif failure.severity == "major":
                score -= 0.20
            else:
                score -= 0.05

        if runtime is not None:
            if not runtime.build_success:
                score -= 0.25
            if not runtime.type_check_success:
                score -= 0.20
            if not runtime.lint_success:
                score -= 0.10

        if visual is not None and not visual.pass_result:
            score -= max(0.10, min(0.40, 1.0 - visual.ssim_score))

        return _clamp(score)

    def _maintainability(
        self,
        normalization: NormalizationReport | None,
        fix_attempts: list[FixAttempt],
    ) -> float:
        score = 1.0
        if normalization is not None:
            score -= min(0.60, normalization.drift_score_after / 10.0)
        score -= min(0.20, len(fix_attempts) * 0.05)
        return _clamp(score)

    def _automation(
        self,
        state: dict[str, Any],
        failures: list[FailureRecord],
    ) -> float:
        score = 1.0 if not failures else 0.70
        if state.get("terminal_state") == "manual-review-required":
            score = min(score, 0.50)

        retry_budget_remaining = int(state.get("retry_budget_remaining", 3))
        score -= max(0, 3 - retry_budget_remaining) * 0.05
        return _clamp(score)

    def _scalability(
        self,
        runtime: RuntimeValidationReport | None,
        visual: VisualRegressionReport | None,
        fix_attempts: list[FixAttempt],
        failures: list[FailureRecord],
    ) -> float:
        score = 1.0
        score -= min(0.25, len(fix_attempts) * 0.05)
        score -= min(0.25, len(failures) * 0.05)

        if runtime is not None and runtime.duration_ms > 60_000:
            score -= 0.10
        if visual is not None and not visual.pass_result:
            score -= 0.10

        return _clamp(score)

    def _grade(self, overall: float) -> Grade:
        if overall >= 0.90:
            return "A"
        if overall >= 0.80:
            return "B"
        if overall >= 0.70:
            return "C"
        if overall >= 0.60:
            return "D"
        return "F"

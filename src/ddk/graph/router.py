"""route_after_validate — pure routing function for LangGraph conditional edge. VALID-04."""

from __future__ import annotations

from typing import Any, Literal, cast

from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport
from ddk.services.failure_signature import failure_signature


def route_after_validate(
    state: dict[str, Any],
) -> Literal["pass", "fix_available", "exhausted"]:
    """Determine next node after validate.

    Args:
        state: Current GraphState dict.

    Returns:
        "pass"          → all checks pass → END
        "fix_available" → failures exist, budget > 0, no oscillation → autofix
        "exhausted"     → budget=0 OR oscillation detected → END (manual-review)

    CRITICAL: Oscillation detection uses failure_signature(), which ignores the per-run
    UUIDs (``failure.id``) but still tells apart different errors in the same file, so
    fixing one of several errors counts as progress, not as oscillation.
    """
    report = cast(RuntimeValidationReport | None, state.get("runtime_validation_report"))
    vis_report = cast(
        VisualRegressionReport | None,
        state.get("visual_regression_report"),
    )

    def _all_passing() -> bool:
        if state.get("terminal_state") == "manual-review-required":
            return False
        if report is None:
            return vis_report is None or vis_report.pass_result
        checks_pass = report.build_success and report.type_check_success and report.lint_success
        if not checks_pass or report.failures:
            return False
        return vis_report is None or vis_report.pass_result

    if _all_passing():
        return "pass"

    # Budget exhausted
    budget: int = state.get("retry_budget_remaining", 0)
    if budget <= 0:
        return "exhausted"

    if state.get("terminal_state") == "manual-review-required":
        return "exhausted"

    # Oscillation: same failure set seen before (signature put there by previous autofix_node)
    failures: list[FailureRecord] = report.failures if report is not None else []
    cur_hash = failure_signature(failures)
    seen = cast(list[int], state.get("failure_hash_history", []))
    if cur_hash in seen:
        return "exhausted"

    return "fix_available"


def route_after_autofix(state: dict[str, Any]) -> Literal["validate", "certify"]:
    """Re-validate after a patch; go straight to certification when a human must take over."""
    if state.get("terminal_state") == "manual-review-required":
        return "certify"
    return "validate"


def route_after_stage(state: dict[str, Any]) -> Literal["continue", "certify"]:
    """Go on to the next stage, or straight to certification once a stage needs a human."""
    if state.get("terminal_state") == "manual-review-required":
        return "certify"
    return "continue"

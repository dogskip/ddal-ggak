"""route_after_validate — pure routing function for LangGraph conditional edge. VALID-04."""
from __future__ import annotations

from typing import Any, Literal, cast

from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport


def _failure_signature(failures: list[FailureRecord]) -> int:
    """Return a stable signature for the current failure set."""
    return hash(
        frozenset((failure.taxonomy_id, failure.file_path or "") for failure in failures)
    )


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

    CRITICAL: Oscillation detection uses hash(frozenset((f.taxonomy_id, f.file_path or "")))
    NOT hash(frozenset(f.id for f in failures)) — UUIDs are regenerated each run!
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
        checks_pass = (
            report.build_success and report.type_check_success and report.lint_success
        )
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

    # Oscillation: same failure pattern seen before (hash put there by previous autofix_node)
    # CORRECT: use (taxonomy_id, file_path) — NOT failure.id (UUID)
    failures: list[FailureRecord] = report.failures if report is not None else []
    cur_hash = _failure_signature(failures)
    seen = cast(list[int], state.get("failure_hash_history", []))
    if cur_hash in seen:
        return "exhausted"

    return "fix_available"

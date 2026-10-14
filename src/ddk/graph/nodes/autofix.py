"""autofix_node — thin adapter: state → AutoFixPlanner → state. D-05. VALID-04.

IMPORTANT: autofix_node appends the current failure hash to failure_hash_history
BEFORE applying the fix. This enables oscillation detection on the next validate cycle:
if the fix fails and the same failures recur, route_after_validate will find the hash
already in history and return "exhausted".
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.services.failure_signature import failure_signature

logger = logging.getLogger(__name__)


async def autofix_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """D-05 thin adapter. Appends failure hash, delegates to AutoFixPlanner, decrements budget.

    Args:
        state: Current GraphState dict.
        **kwargs: LangGraph injects context=ServiceContainer via _wrapper.

    Returns:
        Partial state update with updated fix_attempts, retry_budget_remaining,
        failure_hash_history, and generated_artifacts.
    """
    container = kwargs.get("context")

    # Guard: artifacts must be present to patch
    if state.get("generated_artifacts") is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "autofix_node: generated_artifacts is None — cannot apply patches",
            "current_node": "autofix",
        }

    _report_raw = state.get("runtime_validation_report")
    if _report_raw is not None and not isinstance(_report_raw, RuntimeValidationReport):
        raise TypeError(
            f"autofix_node: runtime_validation_report must be RuntimeValidationReport, "
            f"got {type(_report_raw)!r}"
        )
    report: RuntimeValidationReport | None = _report_raw
    failures: list[FailureRecord] = report.failures if report is not None else []

    # Record current failure signature BEFORE applying fix (failure.id is regenerated each run).
    cur_hash = failure_signature(failures)
    _hist_raw = state.get("failure_hash_history", [])
    if not isinstance(_hist_raw, list):
        raise TypeError(f"autofix_node: failure_hash_history must be list, got {type(_hist_raw)!r}")
    failure_hash_history: list[int] = cast(list[int], _hist_raw)
    updated_history = [*failure_hash_history, cur_hash]

    _attempts_raw = state.get("fix_attempts", [])
    if not isinstance(_attempts_raw, list):
        raise TypeError(f"autofix_node: fix_attempts must be list, got {type(_attempts_raw)!r}")
    existing_attempts: list[FixAttempt] = cast(list[FixAttempt], _attempts_raw)
    attempt_n = len(existing_attempts) + 1
    _arts_raw = state.get("generated_artifacts")
    if _arts_raw is not None and not isinstance(_arts_raw, GeneratedArtifactSet):
        raise TypeError(
            f"autofix_node: generated_artifacts must be GeneratedArtifactSet, "
            f"got {type(_arts_raw)!r}"
        )
    artifacts: GeneratedArtifactSet | None = _arts_raw

    if (
        container is None
        or not hasattr(container, "auto_fix_planner")
        or container.auto_fix_planner is None
    ):
        return {
            "terminal_state": "manual-review-required",
            "error_message": "AutoFixPlanner not configured in ServiceContainer",
            "current_node": "autofix",
        }

    case_id = state.get("case_id", "unknown")
    fix_attempt, patched_artifacts = await container.auto_fix_planner.plan_and_apply(
        failures=failures,
        artifacts=artifacts,
        case_id=case_id,
        attempt_number=attempt_n,
        visual=state.get("visual_regression_report"),
    )
    rollback_controller = getattr(container, "rollback_controller", None)
    checkpoint_creator = getattr(rollback_controller, "create_checkpoint", None)
    if checkpoint_creator is not None and inspect.iscoroutinefunction(checkpoint_creator):
        try:
            checkpoint_ref = await checkpoint_creator(case_id=case_id, attempt_number=attempt_n)
        except (ValueError, OSError) as exc:
            # No git history (plain folder, fresh repository) must not stop the repair loop.
            logger.debug("No checkpoint for attempt %d: %s", attempt_n, exc)
        else:
            fix_attempt = fix_attempt.model_copy(update={"checkpoint_ref": checkpoint_ref})

    result: dict[str, Any] = {
        "generated_artifacts": patched_artifacts,
        "fix_attempts": [*existing_attempts, fix_attempt],
        "retry_budget_remaining": state.get("retry_budget_remaining", 3) - 1,
        "failure_hash_history": updated_history,  # hash recorded here, not in validate_node
        "current_node": "autofix",
    }
    if not fix_attempt.success:
        # Nothing changed, so validating again would only repeat the same failures.
        result["terminal_state"] = "manual-review-required"
        result["error_message"] = (
            f"Auto-fix could not change the code: {fix_attempt.patch_description}"
        )
    return result

"""validate_node — thin adapter: state → RuntimeValidator → state. D-05. VALID-01/02/03.

IMPORTANT: validate_node does NOT update failure_hash_history.
Hash tracking is autofix_node's responsibility. If validate_node appended the hash,
route_after_validate would find cur_hash in seen on the very first cycle and return
"exhausted" before autofix ever runs.
"""
from __future__ import annotations

from typing import Any


async def validate_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """D-05 thin adapter. No business logic — delegates entirely to RuntimeValidator.

    Does NOT touch failure_hash_history (oscillation state managed by autofix_node).

    Args:
        state: Current GraphState dict.
        **kwargs: LangGraph injects context=ServiceContainer via _wrapper.

    Returns:
        Partial state update dict with runtime_validation_report.
        Returns terminal_state="manual-review-required" when validator unavailable.
    """
    container = kwargs.get("context")

    if (
        container is None
        or not hasattr(container, "runtime_validator")
        or container.runtime_validator is None
    ):
        return {
            "terminal_state": "manual-review-required",
            "error_message": "RuntimeValidator not configured in ServiceContainer",
            "current_node": "validate",
        }

    report, vis_report = await container.runtime_validator.run(state)

    result: dict[str, Any] = {
        "runtime_validation_report": report,
        "current_node": "validate",
        # failure_hash_history deliberately NOT updated here
    }
    if vis_report is not None:
        result["visual_regression_report"] = vis_report

    return result

"""Design system node — thin adapter for DesignSystemInferencer (D-05)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer, primary_model_from
from ddk.services.design_system_inferencer import DesignSystemInferencer


async def design_system_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Infer design system tokens and enrich repo_profile.

    Thin adapter: reads state → calls DesignSystemInferencer → writes state.
    No business logic here (D-05).
    """
    container: ServiceContainer | None = kwargs.get("context")
    if container is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    inferencer = DesignSystemInferencer(
        llm=container.llm,
        model=primary_model_from(container),
    )
    case_input = state.get("case_input")
    repo_profile = state.get("repo_profile")
    if case_input is None or repo_profile is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "Missing required upstream state (case_input/repo_profile)",
        }
    design_system = await inferencer.infer(case_input, repo_profile)
    enriched_profile = inferencer.enrich_profile(design_system, repo_profile)
    return {
        "repo_profile": enriched_profile,
        "current_node": "design_system",
    }

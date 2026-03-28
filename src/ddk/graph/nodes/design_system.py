"""Design system node — thin adapter for DesignSystemInferencer (D-05)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.design_system_inferencer import DesignSystemInferencer


async def design_system_node(
    state: dict[str, Any], **kwargs: Any
) -> dict[str, Any]:
    """Infer design system tokens and enrich repo_profile.

    Thin adapter: reads state → calls DesignSystemInferencer → writes state.
    No business logic here (D-05).
    """
    container: ServiceContainer | None = kwargs.get("context")
    if container is None or container.llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    inferencer = DesignSystemInferencer(llm=container.llm)
    design_system = await inferencer.infer(state["case_input"], state["repo_profile"])
    enriched_profile = inferencer.enrich_profile(design_system, state["repo_profile"])
    return {
        "repo_profile": enriched_profile,
        "current_node": "design_system",
    }

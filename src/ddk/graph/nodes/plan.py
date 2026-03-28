"""Plan node — thin adapter for GenerationPlanner (D-05, INGEST-06)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.generation_planner import GenerationPlanner


async def plan_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Create generation plan from intent graph and repo profile.

    Thin adapter: reads state → calls GenerationPlanner service → writes state.
    No business logic (D-05).
    """
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    if llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    planner = GenerationPlanner(llm=llm)
    generation_plan = await planner.plan(
        case_id=state["case_id"],
        intent_graph=state["intent_graph"],
        repo_profile=state["repo_profile"],
        user_prompt=state["case_input"].prompt,
    )
    return {
        "generation_plan": generation_plan,
        "current_node": "plan",
    }

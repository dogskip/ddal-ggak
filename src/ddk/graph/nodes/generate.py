"""Generate node — thin adapter for CodeGenerator (GEN-01)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.code_generator import CodeGenerator


async def generate_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Generate code for each planned node in execution_order.

    Thin adapter: reads state → calls CodeGenerator service → writes state.
    No business logic (GEN-01).
    """
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    if llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    generator = CodeGenerator(llm=llm)
    generated_artifacts = await generator.generate_all(
        plan=state["generation_plan"],
        repo_profile=state["repo_profile"],
        intent_graph=state["intent_graph"],
        prompt=state["case_input"].prompt,
    )
    return {
        "generated_artifacts": generated_artifacts,
        "current_node": "generate",
    }

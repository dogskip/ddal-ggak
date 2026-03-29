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
    generation_plan = state.get("generation_plan")
    repo_profile = state.get("repo_profile")
    intent_graph = state.get("intent_graph")
    case_input = state.get("case_input")
    missing = [
        k
        for k, v in [
            ("generation_plan", generation_plan),
            ("repo_profile", repo_profile),
            ("intent_graph", intent_graph),
            ("case_input", case_input),
        ]
        if v is None
    ]
    if missing:
        return {
            "terminal_state": "manual-review-required",
            "error_message": f"Missing upstream state: {', '.join(missing)}",
        }
    # Pyright cannot narrow through list-comprehension guards above
    assert generation_plan is not None  # guarded above
    assert repo_profile is not None  # guarded above
    assert intent_graph is not None  # guarded above
    assert case_input is not None  # guarded above
    generated_artifacts = await generator.generate_all(
        plan=generation_plan,
        repo_profile=repo_profile,
        intent_graph=intent_graph,
        prompt=case_input.prompt,
    )
    return {
        "generated_artifacts": generated_artifacts,
        "current_node": "generate",
    }

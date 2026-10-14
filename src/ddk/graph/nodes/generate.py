"""Generate node — thin adapter for CodeGenerator (GEN-01)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ddk.graph.context import ServiceContainer, primary_model_from
from ddk.services.code_generator import CodeGenerator
from ddk.services.context_pack_builder import ContextPackBuilder
from ddk.services.images import encode_design_image


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
    generator = CodeGenerator(llm=llm, model=primary_model_from(container))
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
    if generation_plan is None:
        raise RuntimeError("generation_plan is None after guard")
    if repo_profile is None:
        raise RuntimeError("repo_profile is None after guard")
    if intent_graph is None:
        raise RuntimeError("intent_graph is None after guard")
    if case_input is None:
        raise RuntimeError("case_input is None after guard")
    images = [encode_design_image(path) for path in case_input.image_paths]
    repo_root = Path(case_input.repo_path)
    builder = (container.context_pack_builder if container is not None else None) or (
        ContextPackBuilder()
    )
    context = builder.build(generation_plan.target_files, repo_root)
    generated_artifacts = await generator.generate_all(
        plan=generation_plan,
        repo_profile=repo_profile,
        intent_graph=intent_graph,
        prompt=case_input.prompt,
        images=images,
        context=context,
        repo_root=repo_root,
    )
    return {
        "generated_artifacts": generated_artifacts,
        "current_node": "generate",
    }

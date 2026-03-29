"""Normalize node — thin adapter for OutputNormalizer (D-05, CODEGEN-02)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.output_normalizer import OutputNormalizer


async def normalize_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Normalize generated code against repo conventions.

    Thin adapter: reads state → calls OutputNormalizer service → writes state.
    No business logic (D-05).
    Guards against None generated_artifacts (Pitfall 4).
    """
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    if llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }

    if state.get("generated_artifacts") is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "generated_artifacts is None — generate_node may have failed",
        }

    normalizer = OutputNormalizer(llm=llm)
    report, patched_artifacts = await normalizer.normalize(
        artifacts=state["generated_artifacts"],
        repo_profile=state["repo_profile"],
    )
    return {
        "normalization_report": report,
        "generated_artifacts": patched_artifacts,
        "current_node": "normalize",
    }

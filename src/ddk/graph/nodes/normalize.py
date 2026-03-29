"""Normalize node — thin adapter for OutputNormalizer (GEN-02)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.output_normalizer import OutputNormalizer


async def normalize_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Normalize generated artifacts against repository conventions.

    Thin adapter: reads state → calls OutputNormalizer service → writes state.
    No business logic (GEN-02).
    """
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    if llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    generated_artifacts = state.get("generated_artifacts")
    if generated_artifacts is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "generated_artifacts is None — generate node must run first",
        }
    normalizer = OutputNormalizer(llm=llm)
    report, patched = await normalizer.normalize(
        artifacts=generated_artifacts,
        repo_profile=state["repo_profile"],
    )
    return {
        "normalization_report": report,
        "generated_artifacts": patched,
        "current_node": "normalize",
    }

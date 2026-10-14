"""Intent extract node — thin adapter for SemanticIntentExtractor (D-05)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer, primary_model_from
from ddk.services.semantic_intent_extractor import SemanticIntentExtractor


async def intent_extract_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Extract UI intent from screenshot using LLM.

    Thin adapter: reads state → calls SemanticIntentExtractor → writes state.
    No business logic here (D-05).
    """
    container: ServiceContainer | None = kwargs.get("context")
    if container is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "No LLM adapter in ServiceContainer",
        }
    extractor = SemanticIntentExtractor(
        llm=container.llm,
        model=primary_model_from(container),
    )
    case_input = state.get("case_input")
    if case_input is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "Missing upstream state: case_input",
        }
    intent_graph = await extractor.extract(case_input)
    return {
        "intent_graph": intent_graph,
        "current_node": "intent_extract",
    }

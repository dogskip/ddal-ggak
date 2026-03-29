"""Intake node — thin adapter for IntakeProcessor (D-05)."""

from __future__ import annotations

from typing import Any

from ddk.services.intake_processor import IntakeProcessor


async def intake_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Validate case_input and compute image hashes.

    Thin adapter: reads state, calls IntakeProcessor, writes state (D-05).
    No business logic in node.
    """
    processor = IntakeProcessor()
    case_input = state["case_input"]
    validated_input, _ = await processor.process(case_input)
    return {
        "case_input": validated_input,
        "current_node": "intake",
    }

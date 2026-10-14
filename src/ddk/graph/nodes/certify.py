"""Certification node — computes scorecard, release decision, and evidence pack."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from ddk.services.evidence_pack_builder import EvidencePackBuilder
from ddk.services.release_gate import ReleaseGate
from ddk.services.scorecard_calculator import ScorecardCalculator


async def certify_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Compute final certification artifacts from the current pipeline state."""
    recorded = _recorded_llm_usage(state, kwargs.get("context"))
    state = {**state, **recorded}
    scorecard = ScorecardCalculator().calculate(state)
    release_decision = ReleaseGate().decide(state, scorecard)
    evidence_pack = EvidencePackBuilder().build(state, scorecard, release_decision)

    return {
        **recorded,
        "scorecard": scorecard,
        "release_decision": release_decision,
        "evidence_pack": evidence_pack,
        "terminal_state": release_decision.decision,
        "current_node": "certify",
    }


def _recorded_llm_usage(state: dict[str, Any], container: object | None) -> dict[str, Any]:
    """Calls and cost counted by the recording LLM adapter, when the container has one."""
    llm = getattr(container, "llm", None)
    references = getattr(llm, "references", None)
    total_cost = getattr(llm, "total_cost_usd", None)
    if not callable(references) or not isinstance(total_cost, int | float):
        return {}
    return {
        "llm_call_records": cast(Callable[[str], list[str]], references)(str(state["case_id"])),
        "total_cost_usd": float(total_cost),
    }

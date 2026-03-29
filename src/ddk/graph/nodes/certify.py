"""Certification node — computes scorecard, release decision, and evidence pack."""

from __future__ import annotations

from typing import Any

from ddk.services.evidence_pack_builder import EvidencePackBuilder
from ddk.services.release_gate import ReleaseGate
from ddk.services.scorecard_calculator import ScorecardCalculator


async def certify_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Compute final certification artifacts from the current pipeline state."""
    scorecard = ScorecardCalculator().calculate(state)
    release_decision = ReleaseGate().decide(state, scorecard)
    evidence_pack = EvidencePackBuilder().build(state, scorecard, release_decision)

    return {
        "scorecard": scorecard,
        "release_decision": release_decision,
        "evidence_pack": evidence_pack,
        "terminal_state": release_decision.decision,
        "current_node": "certify",
    }

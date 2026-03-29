"""Tests for certify_node."""

from __future__ import annotations

from ddk.graph.nodes.certify import certify_node
from ddk.models.normalization import NormalizationReport
from ddk.models.validation import RuntimeValidationReport


async def test_certify_node_produces_phase5_outputs() -> None:
    result = await certify_node(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
            ),
            "normalization_report": NormalizationReport(case_id="C-001"),
            "fix_attempts": [],
            "retry_budget_remaining": 3,
            "llm_call_records": [],
            "total_cost_usd": 0.0,
            "terminal_state": None,
        }
    )

    assert result["scorecard"] is not None
    assert result["release_decision"] is not None
    assert result["evidence_pack"] is not None
    assert result["release_decision"].decision == "ready"
    assert result["current_node"] == "certify"

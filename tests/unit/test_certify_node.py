"""Tests for certify_node."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

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


class _RecorderStub:
    """Same surface as RecordingLLMAdapter, as far as certify_node cares."""

    total_cost_usd = 0.4321

    def references(self, case_id: str) -> list[str]:
        return [f"llm-call:{case_id}:1", f"llm-call:{case_id}:2"]


async def test_certify_node_takes_calls_and_cost_from_the_recording_llm() -> None:
    container = SimpleNamespace(llm=_RecorderStub())
    state = {
        "case_id": "C-001",
        "runtime_validation_report": RuntimeValidationReport(
            case_id="C-001", build_success=True, type_check_success=True, lint_success=True
        ),
        "fix_attempts": [],
        "retry_budget_remaining": 3,
        "llm_call_records": [],
        "total_cost_usd": 0.0,
        "terminal_state": None,
    }

    result = await certify_node(state, context=container)

    assert result["llm_call_records"] == ["llm-call:C-001:1", "llm-call:C-001:2"]
    assert result["total_cost_usd"] == pytest.approx(0.4321)
    assert result["evidence_pack"].llm_call_record_refs == result["llm_call_records"]
    assert result["evidence_pack"].total_cost_usd == pytest.approx(0.4321)


async def test_certify_node_without_a_recorder_keeps_the_state_values() -> None:
    result = await certify_node(
        {
            "case_id": "C-001",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001", build_success=True, type_check_success=True, lint_success=True
            ),
            "fix_attempts": [],
            "retry_budget_remaining": 3,
            "llm_call_records": ["old-ref"],
            "total_cost_usd": 0.07,
            "terminal_state": None,
        },
        context=SimpleNamespace(llm=object()),
    )

    assert result["evidence_pack"].llm_call_record_refs == ["old-ref"]
    assert result["evidence_pack"].total_cost_usd == pytest.approx(0.07)

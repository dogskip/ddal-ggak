"""Tests for EvidencePackBuilder."""

from __future__ import annotations

from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import RuntimeValidationReport
from ddk.services.evidence_pack_builder import EvidencePackBuilder


def test_build_collects_refs_and_cost_metadata() -> None:
    evidence_pack = EvidencePackBuilder().build(
        {
            "case_id": "C-001",
            "case_input": object(),
            "repo_profile": object(),
            "intent_graph": object(),
            "generation_plan": object(),
            "generated_artifacts": object(),
            "normalization_report": None,
            "runtime_validation_report": RuntimeValidationReport(
                case_id="C-001",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                failures=[],
                duration_ms=1500,
            ),
            "visual_regression_report": None,
            "fix_attempts": [],
            "llm_call_records": ["llm-call:C-001:1"],
            "total_cost_usd": 0.12,
        },
        Scorecard(
            case_id="C-001",
            precision=1.0,
            maintainability=1.0,
            automation=1.0,
            scalability=1.0,
            overall=1.0,
            grade="A",
        ),
        ReleaseDecision(case_id="C-001", decision="ready"),
    )

    assert evidence_pack.input_ref == "case-input:C-001"
    assert evidence_pack.repo_profile_ref == "repo-profile:C-001"
    assert evidence_pack.generation_plan_ref == "generation-plan:C-001"
    assert evidence_pack.runtime_validation_ref == "runtime-validation:C-001"
    assert evidence_pack.total_cost_usd == 0.12
    assert evidence_pack.llm_call_record_refs == ["llm-call:C-001:1"]
    assert evidence_pack.terminal_state == "ready"

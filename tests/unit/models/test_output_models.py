"""Tests for output models: scorecard, release, llm, evidence."""

from __future__ import annotations

import pytest
from datetime import UTC, datetime

from ddk.models.scorecard import Scorecard
from ddk.models.release import BlockerItem, ReleaseDecision
from ddk.models.llm import LLMCallRecord
from ddk.models.evidence import EvidencePack


class TestScorecard:
    def test_scorecard_roundtrip(self) -> None:
        sc = Scorecard(
            case_id="case-001",
            precision=0.95,
            maintainability=0.88,
            automation=0.92,
            scalability=0.80,
            overall=0.89,
            grade="B",
            details={"note": "Good overall"},
        )
        data = sc.model_dump()
        restored = Scorecard.model_validate(data)
        assert restored == sc
        assert restored.grade == "B"
        assert restored.overall == 0.89

    def test_scorecard_rejects_out_of_range(self) -> None:
        with pytest.raises(Exception):  # ValidationError
            Scorecard(
                case_id="case-001",
                precision=1.5,  # out of range
                maintainability=0.5,
                automation=0.5,
                scalability=0.5,
                overall=0.5,
                grade="C",
            )

    def test_scorecard_json_roundtrip(self) -> None:
        sc = Scorecard(
            case_id="c1",
            precision=1.0,
            maintainability=1.0,
            automation=1.0,
            scalability=1.0,
            overall=1.0,
            grade="A",
        )
        json_str = sc.model_dump_json()
        restored = Scorecard.model_validate_json(json_str)
        assert restored == sc


class TestBlockerItem:
    def test_blocker_item_roundtrip(self) -> None:
        blocker = BlockerItem(
            id="BLK-001",
            category="build",
            description="Build fails on TypeScript strict mode",
            severity="critical",
        )
        data = blocker.model_dump()
        restored = BlockerItem.model_validate(data)
        assert restored == blocker
        assert restored.severity == "critical"


class TestReleaseDecision:
    def test_release_decision_roundtrip(self) -> None:
        blockers = [
            BlockerItem(
                id="BLK-001",
                category="build",
                description="Build failure",
                severity="blocker",
            ),
        ]
        rd = ReleaseDecision(
            case_id="case-001",
            decision="blocked",
            scorecard_ref="sc-001",
            blockers=blockers,
            summary="Blocked due to build failure",
            approved_at=None,
        )
        data = rd.model_dump()
        restored = ReleaseDecision.model_validate(data)
        assert restored.case_id == "case-001"
        assert restored.decision == "blocked"
        assert len(restored.blockers) == 1

    def test_release_decision_ready_no_blockers(self) -> None:
        rd = ReleaseDecision(
            case_id="case-001",
            decision="ready",
            scorecard_ref="sc-001",
            approved_at=datetime.now(UTC),
        )
        assert rd.decision == "ready"
        assert rd.blockers == []
        assert rd.approved_at is not None


class TestLLMCallRecord:
    def test_llm_call_record_roundtrip(self) -> None:
        now = datetime.now(UTC)
        record = LLMCallRecord(
            call_id="call-001",
            case_id="case-001",
            node="generation",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            seed=42,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.015,
            schema_version="1.0",
            context_pack_hash="sha256:abc123",
            request_timestamp=now,
            response_timestamp=now,
            duration_ms=2500,
            success=True,
            error_message=None,
        )
        data = record.model_dump()
        restored = LLMCallRecord.model_validate(data)
        assert restored == record
        assert restored.provider == "anthropic"
        assert restored.seed == 42
        assert restored.context_pack_hash == "sha256:abc123"

    def test_llm_call_record_has_reproducibility_fields(self) -> None:
        """CERT-04: Verify all reproducibility fields exist."""
        required_fields = {
            "provider",
            "model",
            "temperature",
            "seed",
            "schema_version",
            "context_pack_hash",
        }
        model_fields = set(LLMCallRecord.model_fields.keys())
        missing = required_fields - model_fields
        assert not missing, f"Missing CERT-04 reproducibility fields: {missing}"

    def test_llm_call_record_json_roundtrip(self) -> None:
        record = LLMCallRecord(
            call_id="c1",
            case_id="case-001",
            node="gen",
            provider="openai",
            model="gpt-4",
        )
        json_str = record.model_dump_json()
        restored = LLMCallRecord.model_validate_json(json_str)
        assert restored == record


class TestEvidencePack:
    def test_evidence_pack_roundtrip(self) -> None:
        ep = EvidencePack(
            case_id="case-001",
            input_ref="input-001",
            repo_profile_ref="rp-001",
            intent_graph_ref="ig-001",
            generation_plan_ref="gp-001",
            artifact_set_ref="as-001",
            normalization_ref="nr-001",
            runtime_validation_ref="rv-001",
            visual_regression_ref="vr-001",
            fix_attempt_refs=["fa-001", "fa-002"],
            scorecard_ref="sc-001",
            release_decision_ref="rd-001",
            llm_call_record_refs=["llm-001", "llm-002"],
            total_cost_usd=0.08,
            pipeline_duration_ms=45000,
            terminal_state="ready",
            schema_version="1.0",
        )
        data = ep.model_dump()
        restored = EvidencePack.model_validate(data)
        assert restored.case_id == "case-001"
        assert len(restored.fix_attempt_refs) == 2
        assert len(restored.llm_call_record_refs) == 2
        assert restored.total_cost_usd == 0.08

    def test_evidence_pack_empty_refs(self) -> None:
        ep = EvidencePack(case_id="case-002")
        assert ep.input_ref is None
        assert ep.fix_attempt_refs == []
        assert ep.llm_call_record_refs == []
        assert ep.total_cost_usd == 0.0
        data = ep.model_dump()
        restored = EvidencePack.model_validate(data)
        assert restored == ep

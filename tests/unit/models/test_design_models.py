"""Roundtrip serialization tests for Design Studio model family."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ddk.models.design_interview import InterviewTurn
from ddk.models.design_requirement import DesignRequirement
from ddk.models.design_document import DesignDocument
from ddk.models.design_compliance import (
    ComplianceCheckItem,
    StandardsComplianceResult,
)
from ddk.models.design_quality import QualityAxisScore, QualityGateScore
from ddk.models.design_package import DesignPackageManifest


# ── InterviewTurn ──────────────────────────────────────────────────


def test_interview_turn_roundtrip():
    turn = InterviewTurn(
        turn_id="IT-001",
        speaker="user",
        message="로그인 화면에 소셜 로그인 버튼이 필요합니다",
        extracted_requirements=["REQ-001", "REQ-003"],
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    json_str = turn.model_dump_json()
    restored = InterviewTurn.model_validate_json(json_str)
    assert restored == turn


def test_interview_turn_defaults():
    turn = InterviewTurn(
        turn_id="IT-002",
        speaker="system",
        message="어떤 기능이 필요한가요?",
    )
    assert turn.extracted_requirements == []
    assert turn.timestamp is not None


# ── DesignRequirement ──────────────────────────────────────────────


def test_design_requirement_roundtrip():
    req = DesignRequirement(
        req_id="REQ-001",
        title="소셜 로그인 지원",
        description="구글, 깃허브 OAuth를 통한 소셜 로그인을 지원해야 한다",
        priority="must",
        acceptance_criteria=["구글 로그인 버튼 존재", "깃허브 로그인 버튼 존재"],
        trace_id="trace-001",
        source_turns=["IT-001"],
    )
    json_str = req.model_dump_json()
    restored = DesignRequirement.model_validate_json(json_str)
    assert restored == req


def test_design_requirement_rejects_empty_criteria():
    with pytest.raises(ValidationError):
        DesignRequirement(
            req_id="REQ-002",
            title="테스트",
            description="설명",
            priority="should",
            acceptance_criteria=[],
        )


def test_design_requirement_rejects_long_title():
    with pytest.raises(ValidationError):
        DesignRequirement(
            req_id="REQ-003",
            title="x" * 201,
            description="설명",
            priority="could",
            acceptance_criteria=["기준1"],
        )


def test_design_requirement_rejects_empty_title():
    with pytest.raises(ValidationError):
        DesignRequirement(
            req_id="REQ-004",
            title="",
            description="설명",
            priority="wont",
            acceptance_criteria=["기준1"],
        )


def test_design_requirement_rejects_long_description():
    with pytest.raises(ValidationError):
        DesignRequirement(
            req_id="REQ-005",
            title="제목",
            description="x" * 2001,
            priority="must",
            acceptance_criteria=["기준1"],
        )


# ── DesignDocument ─────────────────────────────────────────────────


def test_design_document_roundtrip():
    doc = DesignDocument(
        doc_type="SRS",
        standard_ref="IEEE 830",
        title="소프트웨어 요구사항 명세서",
        content_markdown="# SRS\n\n## 1. 개요\n...",
        requirement_refs=["REQ-001", "REQ-002"],
        compliance_score=0.95,
        metadata={"Authority": "AI", "Status": "Draft", "Version": "1.0"},
    )
    json_str = doc.model_dump_json()
    restored = DesignDocument.model_validate_json(json_str)
    assert restored == doc


def test_design_document_defaults():
    doc = DesignDocument(
        doc_type="PRD",
        standard_ref="custom",
        title="제품 요구사항 문서",
        content_markdown="# PRD",
        compliance_score=0.8,
    )
    assert doc.requirement_refs == []
    assert doc.metadata == {}


# ── ComplianceCheckItem ────────────────────────────────────────────


def test_compliance_check_item_roundtrip():
    item = ComplianceCheckItem(
        clause_id="IEEE830-§3.2",
        clause_description="기능 요구사항 섹션",
        status="pass",
        evidence="기능 요구사항 13개 항목 존재",
        remediation=None,
    )
    json_str = item.model_dump_json()
    restored = ComplianceCheckItem.model_validate_json(json_str)
    assert restored == item


def test_compliance_check_item_defaults():
    item = ComplianceCheckItem(
        clause_id="ISO42010-§4.1",
        clause_description="이해관계자 식별",
        status="fail",
    )
    assert item.evidence is None
    assert item.remediation is None


# ── StandardsComplianceResult ──────────────────────────────────────


def test_standards_compliance_result_roundtrip():
    checks = [
        ComplianceCheckItem(
            clause_id="IEEE830-§3.2",
            clause_description="기능 요구사항",
            status="pass",
            evidence="13개 항목 존재",
        ),
        ComplianceCheckItem(
            clause_id="IEEE830-§3.3",
            clause_description="비기능 요구사항",
            status="partial",
            evidence="성능 요구사항 부족",
            remediation="응답 시간 기준 추가",
        ),
    ]
    result = StandardsComplianceResult(
        standard_name="IEEE 830",
        doc_type="SRS",
        checks=checks,
        overall_score=0.85,
        passed=True,
    )
    json_str = result.model_dump_json()
    restored = StandardsComplianceResult.model_validate_json(json_str)
    assert restored == result


# ── QualityAxisScore ───────────────────────────────────────────────


def test_quality_axis_score_roundtrip():
    axis = QualityAxisScore(
        axis="completeness",
        score=4,
        rationale="요구사항의 95% 커버리지",
    )
    json_str = axis.model_dump_json()
    restored = QualityAxisScore.model_validate_json(json_str)
    assert restored == axis


def test_quality_axis_score_rejects_invalid_score():
    with pytest.raises(ValidationError):
        QualityAxisScore(axis="completeness", score=6, rationale="over limit")


# ── QualityGateScore ───────────────────────────────────────────────


def _make_quality_axes() -> list[QualityAxisScore]:
    axes_data = [
        ("completeness", 5, "완벽한 커버리지"),
        ("traceability", 4, "추적 가능"),
        ("implementability", 4, "구현 가능"),
        ("verifiability", 5, "검증 가능"),
        ("operability", 3, "운영 가능"),
        ("compliance", 4, "표준 적합"),
    ]
    return [
        QualityAxisScore(axis=a, score=s, rationale=r) for a, s, r in axes_data
    ]


def test_quality_gate_score_roundtrip():
    axes = _make_quality_axes()
    gate = QualityGateScore(
        axes=axes,
        total_score=25,
        verdict="pass",
        hard_blocks=[],
        recommendations=["운영성 점수 개선 권고"],
    )
    json_str = gate.model_dump_json()
    restored = QualityGateScore.model_validate_json(json_str)
    assert restored == gate


def test_quality_gate_score_rejects_wrong_axis_count():
    axes = _make_quality_axes()[:3]  # only 3 axes
    with pytest.raises(ValidationError):
        QualityGateScore(
            axes=axes,
            total_score=13,
            verdict="flag",
        )


def test_quality_gate_score_rejects_missing_axis():
    """All 6 axis types must be represented."""
    axes = [
        QualityAxisScore(axis="completeness", score=5, rationale="ok"),
        QualityAxisScore(axis="completeness", score=4, rationale="dup"),  # duplicate
        QualityAxisScore(axis="traceability", score=4, rationale="ok"),
        QualityAxisScore(axis="implementability", score=4, rationale="ok"),
        QualityAxisScore(axis="verifiability", score=4, rationale="ok"),
        QualityAxisScore(axis="operability", score=3, rationale="ok"),
    ]
    with pytest.raises(ValidationError):
        QualityGateScore(
            axes=axes,
            total_score=24,
            verdict="pass",
        )


def test_quality_gate_score_defaults():
    axes = _make_quality_axes()
    gate = QualityGateScore(
        axes=axes,
        total_score=25,
        verdict="pass",
    )
    assert gate.hard_blocks == []
    assert gate.recommendations == []


# ── DesignPackageManifest ──────────────────────────────────────────


def _make_design_package_manifest() -> DesignPackageManifest:
    """Helper to create a full DesignPackageManifest for roundtrip tests."""
    turn = InterviewTurn(
        turn_id="IT-001",
        speaker="user",
        message="로그인 화면 필요",
        timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    req = DesignRequirement(
        req_id="REQ-001",
        title="소셜 로그인",
        description="구글 OAuth 로그인 지원",
        priority="must",
        acceptance_criteria=["구글 로그인 버튼 존재"],
        source_turns=["IT-001"],
    )
    doc = DesignDocument(
        doc_type="SRS",
        standard_ref="IEEE 830",
        title="SRS",
        content_markdown="# SRS",
        compliance_score=0.9,
    )
    check = ComplianceCheckItem(
        clause_id="IEEE830-§3.2",
        clause_description="기능 요구사항",
        status="pass",
    )
    compliance = StandardsComplianceResult(
        standard_name="IEEE 830",
        doc_type="SRS",
        checks=[check],
        overall_score=0.9,
        passed=True,
    )
    axes = _make_quality_axes()
    quality = QualityGateScore(
        axes=axes,
        total_score=25,
        verdict="pass",
    )
    return DesignPackageManifest(
        package_id="DP-001",
        project_name="my-app",
        requirements=[req],
        documents=[doc],
        compliance_results=[compliance],
        quality_gate=quality,
        interview_log=[turn],
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def test_design_package_manifest_roundtrip():
    original = _make_design_package_manifest()
    json_str = original.model_dump_json()
    restored = DesignPackageManifest.model_validate_json(json_str)
    assert restored == original


def test_design_package_rejects_empty_requirements():
    with pytest.raises(ValidationError):
        DesignPackageManifest(
            package_id="DP-002",
            project_name="app",
            requirements=[],
            documents=[
                DesignDocument(
                    doc_type="SRS",
                    standard_ref="IEEE 830",
                    title="SRS",
                    content_markdown="# SRS",
                    compliance_score=0.8,
                )
            ],
            compliance_results=[],
            quality_gate=QualityGateScore(
                axes=_make_quality_axes(),
                total_score=25,
                verdict="pass",
            ),
            interview_log=[],
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )


def test_design_package_rejects_empty_documents():
    with pytest.raises(ValidationError):
        DesignPackageManifest(
            package_id="DP-003",
            project_name="app",
            requirements=[
                DesignRequirement(
                    req_id="REQ-001",
                    title="테스트",
                    description="설명",
                    priority="must",
                    acceptance_criteria=["기준1"],
                )
            ],
            documents=[],
            compliance_results=[],
            quality_gate=QualityGateScore(
                axes=_make_quality_axes(),
                total_score=25,
                verdict="pass",
            ),
            interview_log=[],
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class ComplianceCheckItem(DDKBaseModel):
    """표준의 개별 조항에 대한 적합성 검증 항목."""

    clause_id: str  # 조항 식별자 (e.g. "IEEE830-§3.2")
    clause_description: str  # 조항 설명
    status: Literal["pass", "partial", "fail", "not_applicable"]
    evidence: str | None = None  # 적합 증거 또는 위반 상세
    remediation: str | None = None  # 부적합 시 개선 방안


class StandardsComplianceResult(DDKBaseModel):
    """표준 적합성 검증 결과 — 개별 조항 단위 점검과 종합 점수."""

    standard_name: str  # 적용 표준명 (e.g. "IEEE 830", "ISO 42010")
    doc_type: str  # 검증 대상 문서 유형
    checks: list[ComplianceCheckItem]  # 조항별 점검 결과
    overall_score: float = Field(ge=0.0, le=1.0)
    # 종합 적합도 점수
    passed: bool  # 전체 통과 여부

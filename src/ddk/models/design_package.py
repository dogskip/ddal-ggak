from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from ._base import DDKBaseModel
from .design_compliance import StandardsComplianceResult
from .design_document import DesignDocument
from .design_interview import InterviewTurn
from .design_quality import QualityGateScore
from .design_requirement import DesignRequirement


class DesignPackageManifest(DDKBaseModel):
    """설계 패키지 전체 매니페스트 — 인터뷰부터 품질 게이트까지 전 산출물을 포함."""

    package_id: str  # "DP-001" 형식
    project_name: str  # 프로젝트 이름
    requirements: list[DesignRequirement]  # 추출된 요구사항 목록
    documents: list[DesignDocument]  # 생성된 설계문서 목록
    compliance_results: list[StandardsComplianceResult]
    # 표준 적합성 검증 결과
    quality_gate: QualityGateScore  # 6축 품질 게이트 점수
    interview_log: list[InterviewTurn]  # 인터뷰 대화 이력
    created_at: datetime  # 패키지 생성 시각

    @field_validator("requirements")
    @classmethod
    def validate_requirements_non_empty(
        cls,
        v: list[DesignRequirement],
    ) -> list[DesignRequirement]:
        if not v:
            raise ValueError("requirements는 최소 1개 이상이어야 합니다")
        return v

    @field_validator("documents")
    @classmethod
    def validate_documents_non_empty(
        cls,
        v: list[DesignDocument],
    ) -> list[DesignDocument]:
        if not v:
            raise ValueError("documents는 최소 1개 이상이어야 합니다")
        return v

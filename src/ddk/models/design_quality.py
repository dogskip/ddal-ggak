from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from ._base import DDKBaseModel


class QualityAxisScore(DDKBaseModel):
    """6축 품질 검증의 개별 축 점수."""

    axis: Literal[
        "completeness",
        "traceability",
        "implementability",
        "verifiability",
        "operability",
        "compliance",
    ]
    score: int = Field(ge=0, le=5)  # 0~5점
    rationale: str  # 점수 근거


class QualityGateScore(DDKBaseModel):
    """6축 품질 게이트 점수 — 설계 패키지 전체의 품질 판정."""

    axes: list[QualityAxisScore]  # 정확히 6개 축
    total_score: int = Field(ge=0, le=30)  # 6축 합산 (0~30)
    verdict: Literal["pass", "flag", "block"]
    # pass: 전체 통과, flag: 경고 포함 통과, block: 재작업 필요
    hard_blocks: list[str] = Field(default_factory=list)
    # 즉시 수정 필요 항목
    recommendations: list[str] = Field(default_factory=list)
    # 개선 권고 사항

    @field_validator("axes")
    @classmethod
    def validate_six_axes(
        cls, v: list[QualityAxisScore],
    ) -> list[QualityAxisScore]:
        if len(v) != 6:
            raise ValueError("axes는 정확히 6개여야 합니다")
        axis_names = {a.axis for a in v}
        expected = {
            "completeness",
            "traceability",
            "implementability",
            "verifiability",
            "operability",
            "compliance",
        }
        if axis_names != expected:
            raise ValueError(f"axes는 {expected} 각각 하나씩 포함해야 합니다")
        return v

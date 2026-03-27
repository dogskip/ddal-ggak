from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from ._base import DDKBaseModel


class DesignRequirement(DDKBaseModel):
    """구조화된 요구사항 — MoSCoW 우선순위와 인수 기준을 포함."""

    req_id: str  # "REQ-001" 형식
    title: str  # 요구사항 제목 (1~200자)
    description: str  # 상세 설명 (1~2000자)
    priority: Literal["must", "should", "could", "wont"]  # MoSCoW 우선순위
    acceptance_criteria: list[str]  # 인수 기준 (최소 1개)
    trace_id: str | None = None  # upstream trace 식별자
    source_turns: list[str] = Field(default_factory=list)
    # InterviewTurn.turn_id 참조 목록 — 요구사항 출처 추적

    @field_validator("acceptance_criteria")
    @classmethod
    def validate_ac(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("acceptance_criteria는 최소 1개 이상이어야 합니다")
        return v

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 200:
            raise ValueError("title은 1~200자여야 합니다")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 2000:
            raise ValueError("description은 1~2000자여야 합니다")
        return v

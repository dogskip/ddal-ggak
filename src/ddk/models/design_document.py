from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class DesignDocument(DDKBaseModel):
    """생성된 설계문서 하나 — 표준 기반의 마크다운 문서."""

    doc_type: Literal[
        "SRS",
        "PRD",
        "Architecture",
        "API",
        "DBSchema",
        "Security",
        "ADR",
        "TestStrategy",
        "ImplPlan",
        "AIHandoff",
    ]
    standard_ref: str  # 적용 표준 (e.g. "IEEE 830", "ISO 42010", "OpenAPI 3.1")
    title: str  # 문서 제목
    content_markdown: str  # 마크다운 본문
    requirement_refs: list[str] = Field(default_factory=list)
    # 추적된 REQ-XXX ID 목록
    compliance_score: float = Field(ge=0.0, le=1.0)
    # 표준 적합도 (0.0 = 부적합, 1.0 = 완전 적합)
    metadata: dict[str, str] = Field(default_factory=dict)
    # 거버넌스 메타데이터 (e.g. {"Authority": "AI", "Status": "Draft", "Version": "1.0"})

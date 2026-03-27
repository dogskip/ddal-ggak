from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class InterviewTurn(DDKBaseModel):
    """인터뷰 한 턴의 기록 — Design Studio 인터뷰 세션의 개별 대화 단위."""

    turn_id: str  # "IT-001" 형식
    speaker: Literal["system", "user"]  # 발화자
    message: str  # 발화 내용
    extracted_requirements: list[str] = Field(default_factory=list)
    # 이 턴에서 추출된 REQ IDs (e.g. ["REQ-001", "REQ-003"])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class Scorecard(DDKBaseModel):
    case_id: str
    precision: float = Field(ge=0.0, le=1.0)
    maintainability: float = Field(ge=0.0, le=1.0)
    automation: float = Field(ge=0.0, le=1.0)
    scalability: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    grade: Literal["A", "B", "C", "D", "F"]
    details: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

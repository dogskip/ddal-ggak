from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class BlockerItem(DDKBaseModel):
    id: str
    category: str
    description: str
    severity: Literal["critical", "blocker", "major"]


class ReleaseDecision(DDKBaseModel):
    case_id: str
    decision: Literal["ready", "blocked", "manual-review"]
    scorecard_ref: str | None = None
    blockers: list[BlockerItem] = Field(default_factory=list)
    summary: str = ""
    approved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

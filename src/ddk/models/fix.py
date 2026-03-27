from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from ._base import DDKBaseModel


class FixAttempt(DDKBaseModel):
    attempt_number: int = Field(ge=1, le=10)
    case_id: str
    trigger_failures: list[str] = Field(default_factory=list)
    rule_id: str
    files_patched: list[str] = Field(default_factory=list)
    patch_description: str
    success: bool
    remaining_failures: list[str] = Field(default_factory=list)
    checkpoint_ref: str | None = None
    duration_ms: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

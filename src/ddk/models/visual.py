from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class MismatchRegion(DDKBaseModel):
    x: int
    y: int
    width: int
    height: int
    severity: Literal["high", "medium", "low"]


class VisualRegressionReport(DDKBaseModel):
    case_id: str
    reference_path: str
    generated_path: str
    ssim_score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    pass_result: bool
    mismatch_regions: list[MismatchRegion] = []
    diff_image_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

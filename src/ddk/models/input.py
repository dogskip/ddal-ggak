from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field, field_validator

from ._base import DDKBaseModel


class CaseInput(DDKBaseModel):
    case_id: str  # "C-001" 형식
    image_paths: list[Path]  # 최소 1개, 최대 5개
    prompt: str  # 생성 지시 (1~2000자)
    repo_path: Path  # 대상 repo 루트
    reference_notes: str | None = None  # 추가 컨텍스트
    visual_reference_paths: list[Path] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("image_paths")
    @classmethod
    def validate_image_count(cls, v: list[Path]) -> list[Path]:
        if not v:
            raise ValueError("image_paths는 최소 1개 이상이어야 합니다")
        if len(v) > 5:
            raise ValueError("image_paths는 최대 5개까지 허용됩니다")
        return v

    @field_validator("prompt")
    @classmethod
    def validate_prompt_length(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("prompt는 비어 있을 수 없습니다")
        if len(v) > 2000:
            raise ValueError("prompt는 2000자를 초과할 수 없습니다")
        return v

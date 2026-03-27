from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class GenerationNode(DDKBaseModel):
    id: str
    task_description: str
    dependencies: list[str] = Field(default_factory=list)
    output_files: list[str] = Field(default_factory=list)
    validation_hook: str | None = None
    repair_hook: str | None = None
    priority: int = Field(default=1, ge=1, le=5)


class GenerationPlan(DDKBaseModel):
    plan_id: str
    case_id: str
    nodes: list[GenerationNode]
    total_estimated_tokens: int = Field(default=0, ge=0)
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GeneratedFile(DDKBaseModel):
    path: str
    content: str
    language: Literal["typescript", "javascript", "css", "html", "json", "other"] = (
        "typescript"
    )
    source_node_id: str


class GeneratedArtifactSet(DDKBaseModel):
    case_id: str
    files: list[GeneratedFile]
    file_map: dict[str, str] = Field(default_factory=dict)
    generation_trace: list[str] = Field(default_factory=list)
    total_tokens_used: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

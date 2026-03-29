from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field

from ._base import DDKBaseModel


class GenerationNode(DDKBaseModel):
    id: str
    node_type: Literal["file", "component", "hook", "style", "test", "route", "type"]
    target_path: str
    dependencies: list[str] = Field(default_factory=list)
    validation_hooks: list[str] = Field(default_factory=list)
    repair_hooks: list[str] = Field(default_factory=list)
    generation_prompt_hint: str | None = None


class GenerationPlan(DDKBaseModel):
    case_id: str
    nodes: list[GenerationNode]
    execution_order: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    validation_hooks: list[str] = Field(default_factory=list)
    estimated_node_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GeneratedFile(DDKBaseModel):
    path: str
    content: str
    language: Literal["typescript", "javascript", "css", "html", "json", "other"] = "typescript"
    source_node_id: str
    # Design-spec fields (12-data-models.md §4) — additive, defaults provided
    is_new: bool = False
    original_content: str | None = None


class GeneratedArtifactSet(DDKBaseModel):
    case_id: str
    files: list[GeneratedFile]
    file_map: dict[str, str] = Field(default_factory=dict)
    generation_trace: list[str] = Field(default_factory=list)
    total_tokens_used: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Design-spec fields (12-data-models.md §4) — additive, defaults provided
    schema_version: str = "1.0"
    changed_paths: list[str] = Field(default_factory=list)
    trace: dict[str, Any] = Field(default_factory=dict)

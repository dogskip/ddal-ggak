from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from ddk.security.repo_paths import normalize_repo_relative_path

from ._base import DDKBaseModel


class GenerationNode(DDKBaseModel):
    id: str
    node_type: Literal["file", "component", "hook", "style", "test", "route", "type"]
    target_path: str
    dependencies: list[str] = Field(default_factory=list)
    validation_hooks: list[str] = Field(default_factory=list)
    repair_hooks: list[str] = Field(default_factory=list)
    generation_prompt_hint: str | None = None

    @field_validator("target_path")
    @classmethod
    def _normalize_target_path(cls, value: str) -> str:
        return normalize_repo_relative_path(value)


class GenerationPlan(DDKBaseModel):
    case_id: str
    nodes: list[GenerationNode]
    execution_order: list[str] = Field(default_factory=list)
    target_files: list[str] = Field(default_factory=list)
    validation_hooks: list[str] = Field(default_factory=list)
    estimated_node_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("target_files")
    @classmethod
    def _normalize_target_files(cls, values: list[str]) -> list[str]:
        return [normalize_repo_relative_path(value) for value in values]


class GeneratedFile(DDKBaseModel):
    path: str
    content: str
    language: Literal["typescript", "javascript", "css", "html", "json", "other"] = "typescript"
    source_node_id: str
    # Design-spec fields (12-data-models.md §4) — additive, defaults provided
    is_new: bool = False
    original_content: str | None = None

    @field_validator("path")
    @classmethod
    def _normalize_path(cls, value: str) -> str:
        return normalize_repo_relative_path(value)


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

    @field_validator("file_map")
    @classmethod
    def _normalize_file_map(cls, values: dict[str, str]) -> dict[str, str]:
        normalized = {
            normalize_repo_relative_path(path): content for path, content in values.items()
        }
        if len(normalized) != len(values):
            raise ValueError("file_map contains paths that collide after normalization")
        return normalized

    @field_validator("changed_paths")
    @classmethod
    def _normalize_changed_paths(cls, values: list[str]) -> list[str]:
        return [normalize_repo_relative_path(value) for value in values]

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from ._base import DDKBaseModel


class EvidencePack(DDKBaseModel):
    case_id: str
    input_ref: str | None = None
    repo_profile_ref: str | None = None
    intent_graph_ref: str | None = None
    generation_plan_ref: str | None = None
    artifact_set_ref: str | None = None
    normalization_ref: str | None = None
    runtime_validation_ref: str | None = None
    visual_regression_ref: str | None = None
    fix_attempt_refs: list[str] = Field(default_factory=list)
    scorecard_ref: str | None = None
    release_decision_ref: str | None = None
    llm_call_record_refs: list[str] = Field(default_factory=list)
    total_cost_usd: float = Field(default=0.0, ge=0.0)
    pipeline_duration_ms: int = Field(default=0, ge=0)
    terminal_state: str | None = None
    schema_version: str = "1.0"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

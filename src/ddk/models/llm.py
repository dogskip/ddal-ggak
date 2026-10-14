from __future__ import annotations

from datetime import UTC, datetime

from pydantic import Field

from ._base import DDKBaseModel


class LLMCallRecord(DDKBaseModel):
    """Reproducibility metadata for every LLM call — per CERT-04."""

    call_id: str
    case_id: str
    node: str
    provider: str  # "anthropic", "openai", "fake"
    model: str  # e.g. "claude-sonnet-5-5"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    seed: int | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    schema_version: str = "1.0"
    context_pack_hash: str | None = None
    request_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    response_timestamp: datetime | None = None
    duration_ms: int = Field(default=0, ge=0)
    success: bool = True
    error_message: str | None = None

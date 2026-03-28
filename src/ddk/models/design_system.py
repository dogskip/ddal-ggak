"""DesignSystem and InferredDesignToken Pydantic models (INGEST-05)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class InferredDesignToken(DDKBaseModel):
    """A single design token inferred from screenshots and repo analysis."""

    name: str
    value: str
    category: Literal["color", "spacing", "typography", "border_radius", "breakpoint"]
    confidence: float = Field(ge=0.0, le=1.0)


class DesignSystem(DDKBaseModel):
    """Inferred design system for a case, capturing tokens and primitives."""

    case_id: str
    inferred_tokens: list[InferredDesignToken]
    primitive_components: list[str] = Field(default_factory=list)
    token_source: Literal["static", "llm", "hybrid"] = "hybrid"
    schema_version: str = "1.0"

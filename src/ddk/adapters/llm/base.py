"""LLM adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from ddk.models.config import DEFAULT_PRIMARY_MODEL


def _empty_metadata() -> dict[str, Any]:
    return {}


@dataclass
class Message:
    """A single message in an LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str
    images: list[tuple[str, str]] | None = None  # [(base64_data, media_type), ...]


@dataclass
class LLMCallConfig:
    """Configuration for a single LLM call."""

    model: str = DEFAULT_PRIMARY_MODEL
    temperature: float = 0.0  # models that take no sampling settings ignore it
    max_tokens: int = 4096  # size of the answer; models that think get extra room on top
    seed: int | None = None
    response_format: type | None = None  # Pydantic model for structured output
    metadata: dict[str, Any] = field(default_factory=_empty_metadata)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None  # None: model default


@dataclass
class LLMResponse:
    """Response from an LLM call with cost/token metadata."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw_response: dict[str, Any] | None = None
    truncated: bool = False  # the model stopped because it ran out of output tokens


@runtime_checkable
class LLMAdapter(Protocol):
    """Protocol for LLM provider adapters (Anthropic, OpenAI, etc.)."""

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse: ...

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse: ...

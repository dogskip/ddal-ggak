"""LLM adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Message:
    """A single message in an LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMCallConfig:
    """Configuration for a single LLM call."""

    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.0
    max_tokens: int = 4096
    seed: int | None = None
    response_format: type | None = None  # Pydantic model for structured output
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from an LLM call with cost/token metadata."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    raw_response: dict[str, Any] | None = None


@runtime_checkable
class LLMAdapter(Protocol):
    """Protocol for LLM provider adapters (Anthropic, OpenAI, etc.)."""

    async def complete(
        self, messages: list[Message], config: LLMCallConfig
    ) -> LLMResponse: ...

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse: ...

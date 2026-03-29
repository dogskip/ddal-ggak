"""FakeFallbackChain — simulates N provider failures then success."""

from __future__ import annotations

from typing import Any

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message


class FakeFallbackChain:
    """Simulates N provider failures then success."""

    def __init__(self, fail_count: int = 1, success_content: str = "OK"):
        self.fail_count = fail_count
        self.success_content = success_content
        self.attempt = 0
        self.call_log: list[dict[str, Any]] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self.attempt += 1
        self.call_log.append({"attempt": self.attempt, "model": config.model})
        if self.attempt <= self.fail_count:
            raise ConnectionError(f"Provider failed (attempt {self.attempt}/{self.fail_count})")
        return LLMResponse(content=self.success_content, model=config.model)

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        return await self.complete(messages, config)

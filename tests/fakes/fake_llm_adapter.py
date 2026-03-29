"""FakeLLMAdapter — returns canned responses keyed by system prompt first word."""

from __future__ import annotations

import json
from typing import Any

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message


class FakeLLMAdapter:
    """Returns canned responses keyed by system prompt first word. Records all calls."""

    def __init__(self, responses: dict[str, str | dict[str, Any]] | None = None):
        self.responses: dict[str, str | dict[str, Any]] = responses or {}
        self.call_log: list[dict[str, Any]] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        key = self._extract_key(messages)
        self.call_log.append({"key": key, "messages": messages, "config": config})
        if key not in self.responses:
            raise ValueError(f"FakeLLMAdapter: no fixture for key '{key}'")
        content = self.responses[key]
        if isinstance(content, dict):
            content = json.dumps(content)
        return LLMResponse(
            content=content,
            model=config.model,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        return await self.complete(messages, config)

    def _extract_key(self, messages: list[Message]) -> str:
        for msg in messages:
            if msg.role == "system":
                return msg.content.split()[0].lower()
        return "default"

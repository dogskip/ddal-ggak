"""Anthropic Claude LLM adapter."""

from __future__ import annotations

import json
from typing import Any

import anthropic

from .base import LLMAdapter, LLMCallConfig, LLMResponse, Message

# Cost per 1M tokens (USD) — Claude 3.5 Sonnet / Haiku pricing
_COST_TABLE: dict[str, tuple[float, float]] = {
    "claude-3-5-sonnet-20241022": (3.0, 15.0),
    "claude-3-5-sonnet-20240620": (3.0, 15.0),
    "claude-3-5-haiku-20241022": (0.8, 4.0),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-opus-20240229": (15.0, 75.0),
    "claude-opus-4-5": (15.0, 75.0),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_rate, output_rate = _COST_TABLE.get(model, (3.0, 15.0))
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


class ClaudeAdapter:
    """Anthropic Claude adapter implementing the LLMAdapter protocol."""

    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-20241022") -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        """Send messages to Claude and return a text response."""
        model = config.model or self._default_model
        system_prompt, anthropic_messages = _split_messages(messages)

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": anthropic_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response: anthropic.types.Message = await self._client.messages.create(**kwargs)  # type: ignore[call-overload]
        content = _extract_text(response)  # type: ignore[reportUnknownArgumentType]
        usage = response.usage  # type: ignore[reportUnknownMemberType]
        input_tok = int(usage.input_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        output_tok = int(usage.output_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=_estimate_cost(model, input_tok, output_tok),
            raw_response=response.model_dump(),  # type: ignore[arg-type]
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type[Any],
    ) -> LLMResponse:
        """Call Claude with tool_use to force structured JSON output matching output_schema."""
        model = config.model or self._default_model
        system_prompt, anthropic_messages = _split_messages(messages)

        schema: dict[str, Any] = (
            output_schema.model_json_schema()  # type: ignore[union-attr]
            if hasattr(output_schema, "model_json_schema")
            else {}
        )
        tool_name = output_schema.__name__ if hasattr(output_schema, "__name__") else "output"

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "messages": anthropic_messages,
            "tools": [
                {
                    "name": tool_name,
                    "description": f"Output structured {tool_name} data",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response: anthropic.types.Message = await self._client.messages.create(**kwargs)  # type: ignore[call-overload]
        content = _extract_tool_input(response)  # type: ignore[reportUnknownArgumentType]
        usage = response.usage  # type: ignore[reportUnknownMemberType]
        input_tok = int(usage.input_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        output_tok = int(usage.output_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=_estimate_cost(model, input_tok, output_tok),
            raw_response=response.model_dump(),  # type: ignore[arg-type]
        )


def _split_messages(messages: list[Message]) -> tuple[str, list[dict[str, str]]]:
    """Separate system message from user/assistant messages."""
    system = ""
    rest: list[dict[str, str]] = []
    for msg in messages:
        if msg.role == "system":
            system = msg.content
        else:
            rest.append({"role": msg.role, "content": msg.content})
    return system, rest


def _extract_text(response: anthropic.types.Message) -> str:
    for block in response.content:
        if isinstance(block, anthropic.types.TextBlock):
            return block.text
    return ""


def _extract_tool_input(response: anthropic.types.Message) -> str:
    for block in response.content:
        if isinstance(block, anthropic.types.ToolUseBlock):
            return json.dumps(block.input, ensure_ascii=False)
    return "{}"


# Verify the adapter satisfies the protocol at import time
_: LLMAdapter = ClaudeAdapter.__new__(ClaudeAdapter)  # type: ignore[assignment]

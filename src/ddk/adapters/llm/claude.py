"""Anthropic Claude LLM adapter."""

from __future__ import annotations

import json
from typing import Any

import anthropic
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ddk.exceptions import CostCapExceededError

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

    def __init__(
        self,
        api_key: str,
        default_model: str = "claude-3-5-sonnet-20241022",
        cost_cap_usd: float = float("inf"),
    ) -> None:
        if not api_key:
            raise ValueError(
                "ClaudeAdapter requires a non-empty api_key. "
                "Set DDK_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) in the environment."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._default_model = default_model
        self._cost_cap_usd = cost_cap_usd
        self._accumulated_cost: float = 0.0

    def reset_cost_tracking(self) -> None:
        """Reset the accumulated cost counter (e.g. between pipeline runs)."""
        self._accumulated_cost = 0.0

    def _check_cost_cap(self) -> None:
        """Raise CostCapExceededError if the cap has already been reached."""
        if self._accumulated_cost >= self._cost_cap_usd:
            raise CostCapExceededError(
                accumulated_usd=self._accumulated_cost,
                cap_usd=self._cost_cap_usd,
            )

    @retry(
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.InternalServerError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def _messages_create(self, **kwargs: Any) -> anthropic.types.Message:
        """Call messages.create with exponential backoff on 429 / 529 errors."""
        return await self._client.messages.create(**kwargs)  # type: ignore[call-overload,return-value]

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        """Send messages to Claude and return a text response."""
        self._check_cost_cap()
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

        response: anthropic.types.Message = await self._messages_create(**kwargs)
        content = _extract_text(response)  # type: ignore[reportUnknownArgumentType]
        usage = response.usage  # type: ignore[reportUnknownMemberType]
        input_tok = int(usage.input_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        output_tok = int(usage.output_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        cost = _estimate_cost(model, input_tok, output_tok)
        self._accumulated_cost += cost
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            raw_response=response.model_dump(),  # type: ignore[arg-type]
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type[Any],
    ) -> LLMResponse:
        """Call Claude with tool_use to force structured JSON output matching output_schema."""
        self._check_cost_cap()
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

        response: anthropic.types.Message = await self._messages_create(**kwargs)
        content = _extract_tool_input(response)  # type: ignore[reportUnknownArgumentType]
        usage = response.usage  # type: ignore[reportUnknownMemberType]
        input_tok = int(usage.input_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        output_tok = int(usage.output_tokens)  # type: ignore[reportUnknownMemberType,reportUnknownArgumentType]
        cost = _estimate_cost(model, input_tok, output_tok)
        self._accumulated_cost += cost
        return LLMResponse(
            content=content,
            model=model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cost_usd=cost,
            raw_response=response.model_dump(),  # type: ignore[arg-type]
        )


def _split_messages(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Separate system message from user/assistant messages, handling image blocks."""
    system = ""
    rest: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            system = msg.content
        elif msg.images:
            # Build multi-part content with image blocks first, then text
            content_parts: list[dict[str, Any]] = []
            for img_b64, media_type in msg.images:
                content_parts.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": img_b64,
                        },
                    }
                )
            content_parts.append({"type": "text", "text": msg.content})
            rest.append({"role": msg.role, "content": content_parts})
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

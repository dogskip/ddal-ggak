"""Unit tests for cost cap enforcement in ClaudeAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.claude import ClaudeAdapter
from ddk.exceptions import CostCapExceededError


def _make_usage(input_tokens: int = 100, output_tokens: int = 50) -> MagicMock:
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    return usage


def _make_response(
    content: str = "hello",
    input_tokens: int = 100,
    output_tokens: int = 50,
) -> MagicMock:
    msg = MagicMock()
    msg.content = [MagicMock(type="text", text=content)]
    msg.usage = _make_usage(input_tokens, output_tokens)
    msg.model_dump.return_value = {}
    return msg


def _make_adapter(cost_cap_usd: float) -> ClaudeAdapter:
    adapter = ClaudeAdapter(api_key="test-key", cost_cap_usd=cost_cap_usd)
    return adapter


def _basic_messages() -> list[Message]:
    return [Message(role="user", content="hello")]


def _basic_config() -> LLMCallConfig:
    return LLMCallConfig(model="claude-3-haiku-20240307")


class TestCostCapEnforcement:
    async def test_cost_cap_raises_when_exceeded(self) -> None:
        adapter = _make_adapter(cost_cap_usd=0.0)
        adapter._messages_create = AsyncMock(return_value=_make_response())  # type: ignore[attr-defined]
        with pytest.raises(CostCapExceededError):
            await adapter.complete(_basic_messages(), _basic_config())

    async def test_cost_cap_accumulates_across_calls(self) -> None:
        adapter = _make_adapter(cost_cap_usd=999.0)
        response = _make_response(input_tokens=1000, output_tokens=500)
        adapter._messages_create = AsyncMock(return_value=response)  # type: ignore[attr-defined]
        await adapter.complete(_basic_messages(), _basic_config())
        first_cost = adapter._accumulated_cost
        assert first_cost > 0.0
        await adapter.complete(_basic_messages(), _basic_config())
        assert adapter._accumulated_cost > first_cost

    async def test_cost_cap_inf_never_raises(self) -> None:
        adapter = _make_adapter(cost_cap_usd=float("inf"))
        adapter._messages_create = AsyncMock(return_value=_make_response())  # type: ignore[attr-defined]
        for _ in range(5):
            await adapter.complete(_basic_messages(), _basic_config())
        assert adapter._accumulated_cost > 0.0

    async def test_reset_cost_tracking_clears_accumulation(self) -> None:
        adapter = _make_adapter(cost_cap_usd=999.0)
        adapter._messages_create = AsyncMock(return_value=_make_response())  # type: ignore[attr-defined]
        await adapter.complete(_basic_messages(), _basic_config())
        assert adapter._accumulated_cost > 0.0
        adapter.reset_cost_tracking()
        assert adapter._accumulated_cost == 0.0

    async def test_cost_cap_error_message_contains_amounts(self) -> None:
        adapter = _make_adapter(cost_cap_usd=0.0)
        adapter._messages_create = AsyncMock(return_value=_make_response())  # type: ignore[attr-defined]
        with pytest.raises(CostCapExceededError) as exc_info:
            await adapter.complete(_basic_messages(), _basic_config())
        error_msg = str(exc_info.value)
        assert "0.0" in error_msg

    async def test_cost_cap_enforced_in_complete_structured(self) -> None:
        from pydantic import BaseModel

        class Out(BaseModel):
            result: str

        adapter = _make_adapter(cost_cap_usd=0.0)
        with pytest.raises(CostCapExceededError):
            await adapter.complete_structured(_basic_messages(), _basic_config(), Out)

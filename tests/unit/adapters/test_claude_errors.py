"""LLM boundary hardening tests — provider errors map to clean DDK exceptions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.claude import ClaudeAdapter
from ddk.exceptions import (
    LLMAuthenticationError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
)

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _adapter() -> ClaudeAdapter:
    return ClaudeAdapter(api_key="test-key")


def _messages() -> list[Message]:
    return [Message(role="user", content="hi")]


class _Out(BaseModel):
    value: str


class TestErrorMapping:
    async def test_authentication_error_mapped(self) -> None:
        adapter = _adapter()
        err = anthropic.AuthenticationError(
            "invalid x-api-key", response=httpx.Response(401, request=_REQUEST), body=None
        )
        adapter._messages_create = AsyncMock(side_effect=err)  # type: ignore[method-assign]
        with pytest.raises(LLMAuthenticationError):
            await adapter.complete(_messages(), LLMCallConfig())

    async def test_rate_limit_error_mapped(self) -> None:
        adapter = _adapter()
        err = anthropic.RateLimitError(
            "slow down", response=httpx.Response(429, request=_REQUEST), body=None
        )
        adapter._messages_create = AsyncMock(side_effect=err)  # type: ignore[method-assign]
        with pytest.raises(LLMRateLimitError):
            await adapter.complete(_messages(), LLMCallConfig())

    async def test_connection_error_mapped(self) -> None:
        adapter = _adapter()
        err = anthropic.APIConnectionError(message="boom", request=_REQUEST)
        adapter._messages_create = AsyncMock(side_effect=err)  # type: ignore[method-assign]
        with pytest.raises(LLMConnectionError):
            await adapter.complete(_messages(), LLMCallConfig())

    async def test_internal_server_error_mapped_to_connection(self) -> None:
        adapter = _adapter()
        err = anthropic.InternalServerError(
            "upstream", response=httpx.Response(500, request=_REQUEST), body=None
        )
        adapter._messages_create = AsyncMock(side_effect=err)  # type: ignore[method-assign]
        with pytest.raises(LLMConnectionError):
            await adapter.complete(_messages(), LLMCallConfig())


class TestStructuredOutputGuard:
    async def test_missing_tool_block_raises(self) -> None:
        adapter = _adapter()
        # Response with no ToolUseBlock → must raise, not silently return "{}".
        fake = SimpleNamespace(content=[], usage=SimpleNamespace(input_tokens=1, output_tokens=1))
        adapter._messages_create = AsyncMock(return_value=fake)  # type: ignore[method-assign]
        with pytest.raises(LLMResponseError):
            await adapter.complete_structured(_messages(), LLMCallConfig(), _Out)


class TestConfig:
    def test_empty_api_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty api_key"):
            ClaudeAdapter(api_key="")

    def test_timeout_is_configured(self) -> None:
        adapter = ClaudeAdapter(api_key="k", timeout_s=42.0)
        client: Any = adapter._client
        # anthropic stores the timeout; normalize across float / httpx.Timeout forms.
        timeout = client.timeout
        read = getattr(timeout, "read", timeout)
        assert read == pytest.approx(42.0)

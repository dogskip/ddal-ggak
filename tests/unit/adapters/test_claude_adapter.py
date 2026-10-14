"""Tests for ClaudeAdapter — cost tracking, retry, message splitting."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.claude import ClaudeAdapter, _extract_text, _split_messages
from ddk.exceptions import CostCapExceededError
from tests.fakes.claude_client import StreamingClient, reply


class TestClaudeAdapterInit:
    def test_requires_api_key(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            ClaudeAdapter(api_key="")

    def test_creates_with_valid_key(self) -> None:
        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        assert adapter._accumulated_cost == 0.0


class TestCostTracking:
    def test_reset_cost_tracking(self) -> None:
        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        adapter._accumulated_cost = 5.0
        adapter.reset_cost_tracking()
        assert adapter._accumulated_cost == 0.0

    def test_check_cost_cap_raises(self) -> None:
        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        adapter._accumulated_cost = 10.0
        adapter._cost_cap_usd = 5.0
        with pytest.raises(CostCapExceededError):
            adapter._check_cost_cap()

    def test_check_cost_cap_under_limit(self) -> None:
        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        adapter._accumulated_cost = 1.0
        adapter._cost_cap_usd = 5.0
        adapter._check_cost_cap()  # Should not raise


class TestSplitMessages:
    def test_system_separated(self) -> None:
        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        system, api_msgs = _split_messages(messages)
        assert system == "You are helpful"
        assert len(api_msgs) == 1
        assert api_msgs[0]["role"] == "user"

    def test_no_system(self) -> None:
        messages = [
            Message(role="user", content="Hello"),
        ]
        system, api_msgs = _split_messages(messages)
        assert system == ""
        assert len(api_msgs) == 1

    def test_multiple_user_messages(self) -> None:
        messages = [
            Message(role="system", content="sys"),
            Message(role="user", content="q1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="q2"),
        ]
        system, api_msgs = _split_messages(messages)
        assert system == "sys"
        assert len(api_msgs) == 3

    def test_image_content(self) -> None:
        messages = [
            Message(
                role="user",
                content="Look at this",
                images=[("base64data", "image/png")],
            ),
        ]
        _, api_msgs = _split_messages(messages)
        content_parts = api_msgs[0]["content"]
        assert isinstance(content_parts, list)


class TestExtractText:
    def test_string_content(self) -> None:
        import anthropic.types

        block = anthropic.types.TextBlock(type="text", text="hello")
        msg = MagicMock()
        msg.content = [block]
        assert _extract_text(msg) == "hello"

    def test_empty_blocks(self) -> None:
        msg = MagicMock()
        msg.content = []
        assert _extract_text(msg) == ""


class TestClaudeAdapterComplete:
    @pytest.mark.asyncio
    async def test_complete_delegates_to_client(self) -> None:
        import anthropic.types

        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        adapter._cost_cap_usd = 100.0

        content_block = anthropic.types.TextBlock(type="text", text="response text")
        adapter._client = StreamingClient(  # type: ignore[assignment]
            reply(content_block, input_tokens=100, output_tokens=50)
        )

        config = LLMCallConfig(model="claude-3-5-sonnet-20241022")
        messages = [Message(role="user", content="Hi")]
        result = await adapter.complete(messages=messages, config=config)

        assert result.content == "response text"
        assert result.input_tokens == 100


class TestTruncationFlag:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("stop_reason", "expected"), [("max_tokens", True), ("end_turn", False)]
    )
    async def test_complete_reports_when_the_model_ran_out_of_tokens(
        self, stop_reason: str, expected: bool
    ) -> None:
        import anthropic.types

        adapter = ClaudeAdapter(api_key="sk-ant-test-key-123")
        adapter._cost_cap_usd = 100.0
        adapter._client = StreamingClient(  # type: ignore[assignment]
            reply(anthropic.types.TextBlock(type="text", text="partial"), stop_reason=stop_reason)
        )

        result = await adapter.complete(
            messages=[Message(role="user", content="Hi")],
            config=LLMCallConfig(model="claude-3-5-sonnet-20241022"),
        )

        assert result.truncated is expected

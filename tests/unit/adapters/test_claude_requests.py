"""The request the Claude adapter sends, per model family, and how it reads the answer."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest
from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock
from pydantic import BaseModel

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.claude import ClaudeAdapter, _extract_text
from ddk.exceptions import LLMResponseError
from tests.fakes.claude_client import StreamingClient, reply

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


class _Plan(BaseModel):
    value: str


def _text(text: str) -> TextBlock:
    return TextBlock(type="text", text=text)


def _tool(payload: dict[str, Any]) -> ToolUseBlock:
    return ToolUseBlock(type="tool_use", id="toolu_1", name="_Plan", input=payload)


def _adapter(*replies: Any) -> tuple[ClaudeAdapter, StreamingClient]:
    adapter = ClaudeAdapter(api_key="test-key")
    client = StreamingClient(*replies)
    adapter._client = client  # type: ignore[assignment]
    return adapter, client


def _messages() -> list[Message]:
    return [Message(role="system", content="be brief"), Message(role="user", content="go")]


class TestSamplingAndEffort:
    async def test_current_models_are_sent_no_temperature(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert "temperature" not in client.requests[0]

    async def test_older_models_are_still_sent_the_temperature(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(
            _messages(), LLMCallConfig(model="claude-sonnet-4-6", temperature=0.2)
        )

        assert client.requests[0]["temperature"] == 0.2

    async def test_effort_is_sent_when_the_model_supports_it(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(_messages(), LLMCallConfig(model="claude-haiku-5-5", effort="low"))

        assert client.requests[0]["output_config"] == {"effort": "low"}

    async def test_effort_is_left_out_when_the_model_would_reject_it(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(
            _messages(), LLMCallConfig(model="claude-haiku-4-5-20251001", effort="low")
        )

        assert "output_config" not in client.requests[0]

    async def test_effort_is_left_out_when_not_requested(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert "output_config" not in client.requests[0]

    async def test_thinking_models_get_room_for_thinking_on_top_of_the_answer(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(
            _messages(), LLMCallConfig(model="claude-sonnet-5-5", max_tokens=4096, effort="low")
        )

        assert client.requests[0]["max_tokens"] > 4096

    async def test_older_models_keep_the_requested_limit(self) -> None:
        adapter, client = _adapter(reply(_text("ok")))

        await adapter.complete(
            _messages(), LLMCallConfig(model="claude-sonnet-4-6", max_tokens=4096)
        )

        assert client.requests[0]["max_tokens"] == 4096


class TestStreaming:
    async def test_requests_are_streamed_so_long_answers_do_not_hit_the_read_timeout(self) -> None:
        adapter, client = _adapter(reply(_text("done")))

        result = await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert result.content == "done"
        assert client.requests[0]["model"] == "claude-sonnet-5-5"
        assert client.requests[0]["system"] == "be brief"


class TestReadingTheAnswer:
    def test_thinking_blocks_are_skipped_and_text_blocks_are_joined(self) -> None:
        message = reply(
            ThinkingBlock(type="thinking", thinking="hmm", signature="sig"),
            _text("part one, "),
            _text("part two"),
        )

        assert _extract_text(message) == "part one, part two"  # type: ignore[arg-type]

    async def test_running_out_of_tokens_is_reported(self) -> None:
        adapter, _ = _adapter(reply(_text("cut"), stop_reason="max_tokens"))

        result = await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert result.truncated is True

    async def test_running_out_of_context_is_reported_the_same_way(self) -> None:
        adapter, _ = _adapter(reply(_text("cut"), stop_reason="model_context_window_exceeded"))

        result = await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert result.truncated is True

    async def test_a_refusal_is_an_error_with_a_clear_message(self) -> None:
        adapter, _ = _adapter(reply(stop_reason="refusal"))

        with pytest.raises(LLMResponseError, match="declined"):
            await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

    async def test_cost_follows_the_model_price(self) -> None:
        adapter, _ = _adapter(reply(_text("ok"), input_tokens=1_000_000, output_tokens=0))

        result = await adapter.complete(_messages(), LLMCallConfig(model="claude-sonnet-5-5"))

        assert result.cost_usd == pytest.approx(2.0)


class TestStructuredAnswers:
    async def test_models_that_reject_a_forced_tool_are_asked_to_call_it(self) -> None:
        adapter, client = _adapter(reply(_tool({"value": "x"})))

        result = await adapter.complete_structured(
            _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
        )

        request = client.requests[0]
        assert request["tool_choice"] == {"type": "auto"}
        assert "_Plan" in request["system"]
        assert request["system"].startswith("be brief")
        assert json.loads(result.content) == {"value": "x"}

    @pytest.mark.parametrize("model", ["claude-sonnet-4-6", "claude-haiku-5-5"])
    async def test_models_that_accept_it_get_a_forced_tool(self, model: str) -> None:
        adapter, client = _adapter(reply(_tool({"value": "x"})))

        await adapter.complete_structured(_messages(), LLMCallConfig(model=model), _Plan)

        assert client.requests[0]["tool_choice"] == {"type": "tool", "name": "_Plan"}
        assert client.requests[0]["system"] == "be brief"

    async def test_the_instruction_works_without_a_system_prompt(self) -> None:
        adapter, client = _adapter(reply(_tool({"value": "x"})))

        await adapter.complete_structured(
            [Message(role="user", content="go")], LLMCallConfig(model="claude-sonnet-5-5"), _Plan
        )

        assert "_Plan" in client.requests[0]["system"]

    async def test_json_in_plain_text_is_accepted_when_the_tool_is_skipped(self) -> None:
        adapter, _ = _adapter(reply(_text('Here you go:\n```json\n{"value": "x"}\n```')))

        result = await adapter.complete_structured(
            _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
        )

        assert json.loads(result.content) == {"value": "x"}

    async def test_thinking_before_the_tool_call_is_ignored(self) -> None:
        adapter, _ = _adapter(
            reply(ThinkingBlock(type="thinking", thinking="", signature="s"), _tool({"value": "y"}))
        )

        result = await adapter.complete_structured(
            _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
        )

        assert json.loads(result.content) == {"value": "y"}

    async def test_no_tool_call_and_no_json_is_an_error(self) -> None:
        adapter, _ = _adapter(reply(_text("I cannot do that")))

        with pytest.raises(LLMResponseError, match="_Plan"):
            await adapter.complete_structured(
                _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
            )

    async def test_a_cut_off_structured_answer_is_an_error_not_partial_data(self) -> None:
        adapter, _ = _adapter(reply(_tool({"value": "par"}), stop_reason="max_tokens"))

        with pytest.raises(LLMResponseError, match="max_tokens"):
            await adapter.complete_structured(
                _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
            )

    async def test_a_refusal_is_an_error_with_a_clear_message(self) -> None:
        adapter, _ = _adapter(reply(stop_reason="refusal"))

        with pytest.raises(LLMResponseError, match="declined"):
            await adapter.complete_structured(
                _messages(), LLMCallConfig(model="claude-sonnet-5-5"), _Plan
            )


class TestProviderErrors:
    async def test_unknown_model_points_at_the_setting(self) -> None:
        adapter = ClaudeAdapter(api_key="test-key")
        err = anthropic.NotFoundError(
            "model: claude-nope", response=httpx.Response(404, request=_REQUEST), body=None
        )
        adapter._messages_create = AsyncMock(side_effect=err)  # type: ignore[method-assign]

        with pytest.raises(LLMResponseError, match=r"claude-nope.*DDK_LLM_MODEL"):
            await adapter.complete(_messages(), LLMCallConfig(model="claude-nope"))


async def test_budgeted_completion_keeps_exact_reserved_output_limit():
    adapter, client = _adapter(reply(_text("proposal")))
    result = await adapter.complete_bounded(_messages(), model="claude-sonnet-5-5", max_tokens=512)
    assert result.content == "proposal"
    assert len(client.requests) == 1
    assert client.requests[0]["max_tokens"] == 512
    assert "tools" not in client.requests[0]
    assert result.input_tokens >= 0


async def test_budgeted_completion_uses_the_observed_model_identity():
    observed = reply(_text("proposal"))
    observed.model = "claude-haiku-4-5"
    adapter, _ = _adapter(observed)
    result = await adapter.complete_bounded(_messages(), model="claude-sonnet-5-5", max_tokens=512)
    assert result.model == "claude-haiku-4-5"

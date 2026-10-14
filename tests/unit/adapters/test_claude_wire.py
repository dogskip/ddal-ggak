"""The real Anthropic SDK against a stand-in server: what goes over the wire, and how a
streamed reply is read back. No network, no API key.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import pytest
from pydantic import BaseModel

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.claude import ClaudeAdapter


class _Plan(BaseModel):
    value: str


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _stream(blocks: list[str], *, stop_reason: str = "end_turn") -> str:
    """A complete streamed reply: 25 input tokens, 15 output tokens."""
    head = _event(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "m",
                "content": [],
                "stop_reason": None,
                "stop_sequence": None,
                "usage": {"input_tokens": 25, "output_tokens": 1},
            },
        },
    )
    tail = _event(
        "message_delta",
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 15},
        },
    ) + _event("message_stop", {"type": "message_stop"})
    return head + "".join(blocks) + tail


def _block(index: int, start: dict[str, Any], *deltas: dict[str, Any]) -> str:
    out = _event(
        "content_block_start",
        {"type": "content_block_start", "index": index, "content_block": start},
    )
    for delta in deltas:
        out += _event(
            "content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}
        )
    return out + _event("content_block_stop", {"type": "content_block_stop", "index": index})


_THINKING = _block(
    0,
    {"type": "thinking", "thinking": "", "signature": ""},
    {"type": "thinking_delta", "thinking": "Let me think."},
    {"type": "signature_delta", "signature": "sig"},
)


def _adapter(sse: str, sent: list[dict[str, Any]]) -> ClaudeAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse.encode()
        )

    adapter = ClaudeAdapter(api_key="test-key")
    adapter._client = anthropic.AsyncAnthropic(
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return adapter


async def test_a_streamed_answer_with_thinking_is_read_back_and_priced() -> None:
    sent: list[dict[str, Any]] = []
    text = _block(
        1,
        {"type": "text", "text": ""},
        {"type": "text_delta", "text": "Hel"},
        {"type": "text_delta", "text": "lo"},
    )
    adapter = _adapter(_stream([_THINKING, text]), sent)

    result = await adapter.complete(
        [Message(role="system", content="be brief"), Message(role="user", content="hi")],
        LLMCallConfig(model="claude-sonnet-5-5", max_tokens=4096, effort="low"),
    )

    assert result.content == "Hello"
    assert (result.input_tokens, result.output_tokens) == (25, 15)
    assert result.cost_usd == pytest.approx((25 * 2 + 15 * 10) / 1_000_000)
    assert result.truncated is False
    body = sent[0]
    assert body["stream"] is True
    assert body["model"] == "claude-sonnet-5-5"
    assert body["max_tokens"] == 4096 + 2048
    assert body["output_config"] == {"effort": "low"}
    assert body["system"] == "be brief"
    assert "temperature" not in body


async def test_a_tool_call_streamed_in_pieces_is_assembled() -> None:
    sent: list[dict[str, Any]] = []
    tool = _block(
        1,
        {"type": "tool_use", "id": "toolu_1", "name": "_Plan", "input": {}},
        {"type": "input_json_delta", "partial_json": '{"val'},
        {"type": "input_json_delta", "partial_json": 'ue": "x"}'},
    )
    adapter = _adapter(_stream([_THINKING, tool], stop_reason="tool_use"), sent)

    result = await adapter.complete_structured(
        [Message(role="user", content="go")], LLMCallConfig(model="claude-sonnet-5-5"), _Plan
    )

    assert json.loads(result.content) == {"value": "x"}
    body = sent[0]
    assert body["tool_choice"] == {"type": "auto"}
    assert body["tools"][0]["name"] == "_Plan"
    assert "_Plan" in body["system"]
    assert "temperature" not in body


async def test_an_older_model_gets_temperature_and_a_forced_tool() -> None:
    sent: list[dict[str, Any]] = []
    tool = _block(
        0,
        {"type": "tool_use", "id": "toolu_1", "name": "_Plan", "input": {}},
        {"type": "input_json_delta", "partial_json": '{"value": "y"}'},
    )
    adapter = _adapter(_stream([tool], stop_reason="tool_use"), sent)

    result = await adapter.complete_structured(
        [Message(role="user", content="go")],
        LLMCallConfig(model="claude-sonnet-4-6", temperature=0.0, max_tokens=2048),
        _Plan,
    )

    assert json.loads(result.content) == {"value": "y"}
    body = sent[0]
    assert body["temperature"] == 0.0
    assert body["tool_choice"] == {"type": "tool", "name": "_Plan"}
    assert body["max_tokens"] == 2048
    assert "output_config" not in body


async def test_a_reply_that_hit_the_token_limit_is_flagged() -> None:
    sent: list[dict[str, Any]] = []
    text = _block(0, {"type": "text", "text": ""}, {"type": "text_delta", "text": "cut"})
    adapter = _adapter(_stream([text], stop_reason="max_tokens"), sent)

    result = await adapter.complete(
        [Message(role="user", content="hi")], LLMCallConfig(model="claude-haiku-5-5")
    )

    assert (result.content, result.truncated) == ("cut", True)

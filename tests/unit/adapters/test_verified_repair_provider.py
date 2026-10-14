"""Usage settlement must not guess away cache or server-tool charges."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ddk.adapters.llm.base import LLMResponse
from ddk.adapters.verified_repair_provider import ClaudeRepairProvider
from ddk.services.verified_repair import RepairRequest


def request():
    return RepairRequest("case", 0, "claude-sonnet-5-5", "system", "fixed prompt", 4096, 512)


@pytest.mark.parametrize(
    "extra,known",
    [
        ({"cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}, True),
        ({"cache_creation_input_tokens": 1, "cache_read_input_tokens": 0}, False),
        ({"cache_creation_input_tokens": 0, "cache_read_input_tokens": 2}, False),
        ({}, False),
        (
            {
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "service_tier": "priority",
            },
            False,
        ),
    ],
)
async def test_only_explicit_supported_usage_can_be_settled(extra, known):
    client = AsyncMock()
    client.complete_bounded.return_value = LLMResponse(
        '{"files":[]}',
        "claude-sonnet-5-5",
        raw_response={"usage": {"input_tokens": 3, "output_tokens": 4, **extra}},
    )
    result = await ClaudeRepairProvider(client)(request())
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 4
    assert (result.usage.extra_micro_usd == 0) is known
    client.complete_bounded.assert_awaited_once()
    assert client.complete_bounded.call_args.kwargs["max_tokens"] == 512


async def test_truncation_is_reported_after_observed_usage():
    client = AsyncMock()
    client.complete_bounded.return_value = LLMResponse(
        "partial",
        "claude-sonnet-5-5",
        truncated=True,
        raw_response={
            "usage": {
                "input_tokens": 1,
                "output_tokens": 2,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
            }
        },
    )
    result = await ClaudeRepairProvider(client)(request())
    assert result.value.truncated
    assert result.usage.extra_micro_usd == 0

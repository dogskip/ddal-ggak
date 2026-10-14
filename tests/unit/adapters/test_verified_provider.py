from __future__ import annotations

import pytest

from ddk.adapters.verified_provider import (
    ClaudeCliProvider,
    CodexCliProvider,
    OpenAICompatibleProvider,
    default_price,
    select_price,
)
from ddk.services.verified_repair import RepairRequest


def request():
    return RepairRequest("case", 0, "model-v1", "system", "{}", 1000, 100)


async def test_openai_compatible_requires_observed_usage_and_bounds_output():
    seen = []

    async def transport(url, payload, headers):
        seen.append(payload)
        return {
            "model": "model-v1",
            "choices": [{"message": {"content": '{"files":[]}'}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 2,
                "completion_tokens": 3,
                "total_tokens": 5,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        }

    result = await OpenAICompatibleProvider("http://127.0.0.1:1234/v1", transport=transport)(
        request()
    )
    assert seen[0]["max_tokens"] == 100
    assert result.usage.input_tokens == 2 and result.usage.extra_micro_usd == 0

    async def missing(*args):
        return {
            "model": "model-v1",
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
        }

    result = await OpenAICompatibleProvider("http://127.0.0.1:1234/v1", transport=missing)(
        request()
    )
    assert result.usage is None


@pytest.mark.parametrize("factory", [ClaudeCliProvider, CodexCliProvider])
async def test_cli_bridge_does_not_invent_zero_usage_or_cost(factory):
    calls = []

    async def runner(argv, payload):
        calls.append((argv, payload))
        return b'{"result":"{\\"files\\":[]}","model":"model-v1"}'

    result = await factory(runner=runner)(request())
    assert result.usage is None and calls
    assert not any("dangerously" in arg for arg in calls[0][0])
    if factory is CodexCliProvider:
        assert "--ignore-user-config" in calls[0][0]
        assert "--ignore-rules" in calls[0][0]


def test_default_price_is_case_bound_and_has_dated_evidence():
    price = default_price("claude-sonnet-5-5", "a" * 64)
    assert price.evaluator_sha256 == "a" * 64 and price.input_micro_usd_per_million > 0


@pytest.mark.parametrize(
    ("provider", "endpoint", "override", "code"),
    [
        ("unknown", None, None, "invalid_provider_selection"),
        ("anthropic", "https://unapproved.example", None, "invalid_provider_selection"),
        ("openai-compatible", None, None, "invalid_provider_selection"),
        ("codex-cli", None, None, "price_override_required"),
        ("claude-cli", None, None, "price_override_required"),
        ("openai-compatible", "http://127.0.0.1:1234", None, "price_override_required"),
        ("anthropic", None, {}, "price_invalid"),
    ],
)
def test_quote_selection_cannot_guess_another_provider_price(provider, endpoint, override, code):
    with pytest.raises(ValueError, match=code):
        select_price(provider, "a" * 64, override, endpoint=endpoint)


async def test_owned_transport_runs_real_process_and_collects_exact_bytes():
    import sys

    from ddk.adapters.verified_provider import _owned

    result = await _owned(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        b"bounded",
    )
    assert result == b"bounded"


@pytest.mark.parametrize("days", [-1, 31])
def test_default_price_rejects_future_and_expired_evidence(monkeypatch, days):
    from datetime import UTC, datetime, timedelta

    import ddk.adapters.verified_provider as module

    timestamp = datetime.now(UTC) - timedelta(days=days)
    monkeypatch.setattr(module, "PRICE_VERIFIED_AT", timestamp.isoformat().replace("+00:00", "Z"))
    with pytest.raises(ValueError, match="price_override_required"):
        default_price("claude-sonnet-5-5", "a" * 64)

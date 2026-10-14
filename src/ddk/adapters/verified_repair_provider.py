"""One bounded Anthropic attempt, with explicitly observed linear usage only."""

from __future__ import annotations

from typing import cast

from ddk.adapters.llm.base import Message
from ddk.adapters.llm.claude import ClaudeAdapter
from ddk.models.verified_change import Record, canonical_json
from ddk.services.verified_budget import ProviderResult, ProviderUsage
from ddk.services.verified_repair import RepairReply, RepairRequest


def _linear_usage(usage: Record) -> bool:
    for key in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        if type(usage.get(key)) is not int or usage[key] != 0:
            return False
    if usage.get("service_tier") not in (None, "standard"):
        return False
    if usage.get("inference_geo") not in (None, "global"):
        return False
    for key in ("server_tool_use", "cache_creation"):
        group = usage.get(key)
        if group is not None and (not isinstance(group, dict) or any(cast(Record, group).values())):
            return False
    supported = {
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
        "server_tool_use",
        "cache_creation",
        "service_tier",
        "inference_geo",
        "output_tokens_details",
    }
    return not any(value is not None for key, value in usage.items() if key not in supported)


class ClaudeRepairProvider:
    """Convert one bounded reply into observed usage and a source proposal."""

    def __init__(self, client: ClaudeAdapter) -> None:
        self.client = client

    async def __call__(self, request: RepairRequest) -> ProviderResult:
        result = await self.client.complete_bounded(
            [Message("system", request.system), Message("user", request.prompt)],
            model=request.model,
            max_tokens=request.output_limit,
        )
        try:
            output_bytes = max(
                len(canonical_json(result.raw_response)), len(result.content.encode())
            )
        except (ValueError, UnicodeError):
            output_bytes = None
        raw = (result.raw_response or {}).get("usage")
        usage = cast(Record, raw) if isinstance(raw, dict) else {}
        return ProviderResult(
            RepairReply(result.content, result.truncated, output_bytes),
            ProviderUsage(
                usage.get("input_tokens"),
                usage.get("output_tokens"),
                0 if _linear_usage(usage) else None,
            ),
            "anthropic",
            result.model,
        )

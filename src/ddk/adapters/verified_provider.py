"""Bounded provider transports; unobserved CLI billing never settles as zero."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

from ddk.adapters.subprocess_build_runner import start_owned_process, stop_owned_process
from ddk.adapters.verified_repair_provider import ClaudeRepairProvider as AnthropicMessagesProvider
from ddk.models.verified_change import (
    Record,
    canonical_json,
    decode_json,
    object_record,
    object_records,
)
from ddk.services.verified_budget import ProviderResult, ProviderUsage, VerifiedPrice
from ddk.services.verified_repair import RepairProvider, RepairReply, RepairRequest

DEFAULT_PRICES: dict[str, tuple[int, int]] = {
    "claude-sonnet-5-5": (2_000_000, 10_000_000),
    "claude-opus-5-5": (4_000_000, 20_000_000),
    "claude-haiku-5-5": (500_000, 2_500_000),
}
PRICE_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICE_VERIFIED_AT = "2026-10-14T18:48:38Z"
PROVIDERS = frozenset({"anthropic", "openai-compatible", "claude-cli", "codex-cli"})


def default_price(model: str, evaluator_sha256: str) -> VerifiedPrice:
    date = datetime.fromisoformat(PRICE_VERIFIED_AT.replace("Z", "+00:00"))
    age = datetime.now(UTC) - date
    if model not in DEFAULT_PRICES or not timedelta(0) <= age <= timedelta(days=30):
        raise ValueError("price_override_required")
    input_price, output_price = DEFAULT_PRICES[model]
    return VerifiedPrice(
        "anthropic",
        model,
        input_price,
        output_price,
        0,
        PRICE_SOURCE,
        PRICE_VERIFIED_AT,
        evaluator_sha256,
    )


async def _owned(argv: list[str], payload: bytes) -> bytes:
    if len(payload) > 2 * 1024**2:
        raise ValueError("provider_input_limit")
    allowed = {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TMPDIR",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    if argv and Path(argv[0]).name == "claude":
        allowed.add("ANTHROPIC_API_KEY")
    if argv and Path(argv[0]).name == "codex":
        allowed.add("OPENAI_API_KEY")
    environment = {k: v for k, v in os.environ.items() if k in allowed}
    with tempfile.TemporaryDirectory(prefix="ddk-provider-") as folder:
        process, output = await start_owned_process(
            argv,
            Path(folder),
            stdin=asyncio.subprocess.PIPE,
            environment=environment,
            max_output_bytes=2 * 1024**2,
        )
        try:
            async with asyncio.timeout(60):
                assert process.stdin is not None
                process.stdin.write(payload)
                await process.stdin.drain()
                process.stdin.close()
                exceeded = await output.wait(time.monotonic_ns() + 60_000_000_000)
                if exceeded:
                    raise ValueError("provider_output_limit")
                if process.returncode != 0:
                    raise ValueError("provider_process_failed")
                return bytes(output.stdout)
        finally:
            await stop_owned_process(process, output)


Transport = Callable[[str, Record, dict[str, str]], Awaitable[Record]]
Runner = Callable[[list[str], bytes], Awaitable[bytes]]
_HTTP_WORKER = """import json,sys,urllib.request
v=json.load(sys.stdin)
class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None
request=urllib.request.Request(v['url'],json.dumps(v['payload']).encode(),v['headers'],method='POST')
with urllib.request.build_opener(NoRedirect()).open(request,timeout=30) as response:
 data=response.read(2097153)
 if len(data)>2097152:raise ValueError('provider_output_limit')
 sys.stdout.buffer.write(data)
"""


async def _post(url: str, payload: Record, headers: dict[str, str]) -> Record:
    raw = await _owned(
        [sys.executable, "-I", "-c", _HTTP_WORKER],
        canonical_json({"url": url, "payload": payload, "headers": headers}),
    )
    return decode_json(raw)


class OpenAICompatibleProvider:
    def __init__(
        self, base_url: str, *, api_key: str | None = None, transport: Transport = _post
    ) -> None:
        url = urlsplit(base_url)
        if (
            url.scheme not in {"https", "http"}
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (url.scheme == "http" and url.hostname not in {"127.0.0.1", "::1", "localhost"})
        ):
            raise ValueError("invalid_provider_endpoint")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.key = api_key
        self.transport = transport

    async def __call__(self, request: RepairRequest) -> ProviderResult:
        payload = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
            "max_tokens": request.output_limit,
            "stream": False,
            "n": 1,
        }
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        reply = await self.transport(self.url, payload, headers)
        choices = object_records(reply.get("choices"))
        if len(choices) != 1:
            raise ValueError("provider_response_invalid")
        choice = choices[0]
        message = object_record(choice.get("message"))
        content = message.get("content")
        if not isinstance(content, str) or not isinstance(reply.get("model"), str):
            raise ValueError("provider_response_invalid")
        counts = reply.get("usage")
        usage = None
        if counts is not None:
            counts = object_record(counts)
            details = object_record(counts.get("prompt_tokens_details", {}))
            known = all(
                type(counts.get(k)) is int and counts[k] >= 0
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")
            )
            known = known and counts.get("total_tokens") == counts.get(
                "prompt_tokens", 0
            ) + counts.get("completion_tokens", 0)
            known = (
                known
                and type(details.get("cached_tokens")) is int
                and details["cached_tokens"] == 0
                and set(details) <= {"cached_tokens", "audio_tokens"}
                and details.get("audio_tokens", 0) == 0
            )
            completion = object_record(counts.get("completion_tokens_details") or {})
            known = known and (
                set(completion)
                <= {
                    "reasoning_tokens",
                    "audio_tokens",
                    "accepted_prediction_tokens",
                    "rejected_prediction_tokens",
                }
                and completion.get("audio_tokens", 0) == 0
                and completion.get("accepted_prediction_tokens", 0) == 0
                and completion.get("rejected_prediction_tokens", 0) == 0
            )
            known = (
                known
                and not message.get("tool_calls")
                and reply.get("service_tier") in (None, "default")
            )
            known = known and set(counts) <= {
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
                "prompt_tokens_details",
                "completion_tokens_details",
            }
            if known:
                usage = ProviderUsage(counts["prompt_tokens"], counts["completion_tokens"], 0)
        return ProviderResult(
            RepairReply(content, choice.get("finish_reason") != "stop", len(canonical_json(reply))),
            usage,
            "openai-compatible",
            reply["model"],
        )


class ClaudeCliProvider:
    def __init__(self, *, runner: Runner = _owned) -> None:
        self.runner = runner

    async def __call__(self, request: RepairRequest) -> ProviderResult:
        argv = [
            "claude",
            "--print",
            "--output-format",
            "json",
            "--safe-mode",
            "--restricted",
            "--model",
            request.model,
            "--tools",
            "",
            "--disable-slash-commands",
            "--no-session-persistence",
            "--setting-sources",
            "",
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
            "--settings",
            '{"disableAllHooks":true}',
            "--max-turns",
            "1",
        ]
        raw = await self.runner(argv, (request.system + "\n" + request.prompt).encode())
        reply = decode_json(raw)
        content = reply.get("result")
        if not isinstance(content, str):
            raise ValueError("provider_response_invalid")
        return ProviderResult(
            RepairReply(content, False, len(raw)),
            None,
            "claude-cli",
            reply.get("model", "unobserved"),
        )


class CodexCliProvider:
    def __init__(self, *, runner: Runner = _owned) -> None:
        self.runner = runner

    async def __call__(self, request: RepairRequest) -> ProviderResult:
        argv = [
            "codex",
            "exec",
            "--sandbox",
            "read-only",
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--skip-git-repo-check",
            "--json",
            "-m",
            request.model,
        ]
        for feature in (
            "shell_tool",
            "unified_exec",
            "shell_snapshot",
            "code_mode",
            "code_mode_host",
            "browser_use",
            "browser_use_external",
            "computer_use",
            "view_image",
            "image_generation",
            "apps",
            "plugins",
            "remote_plugin",
            "hooks",
            "memories",
            "multi_agent",
            "multi_agent_v2",
        ):
            argv += ["--disable", feature]
        for setting in (
            'web_search="disabled"',
            "project_doc_max_bytes=0",
            "mcp_servers={}",
            'approval_policy="never"',
            'shell_environment_policy.inherit="none"',
        ):
            argv += ["-c", setting]
        argv += ["--strict-config", "-"]
        raw = await self.runner(argv, (request.system + "\n" + request.prompt).encode())
        rows = [decode_json(line) for line in raw.splitlines() if line.strip()]
        content = None
        model = "unobserved"
        for row in rows:
            if isinstance(row.get("result"), str):
                content = row["result"]
                model = row.get("model", model)
            item = object_record(row.get("item", {}))
            if item.get("type") == "agent_message":
                content = item.get("text")
        if not isinstance(content, str):
            raise ValueError("provider_response_invalid")
        return ProviderResult(RepairReply(content, False, len(raw)), None, "codex-cli", model)


def provider_for(kind: str, endpoint: str | None = None) -> RepairProvider:
    if kind == "anthropic":
        key = os.environ.get("DDK_ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("provider_api_key_required")

        async def call(request: RepairRequest) -> ProviderResult:
            from ddk.adapters.llm.claude import ClaudeAdapter

            client = ClaudeAdapter(api_key=key)
            try:
                return await AnthropicMessagesProvider(client)(request)
            finally:
                await client.close()

        return call
    if kind == "claude-cli":
        return ClaudeCliProvider()
    if kind == "codex-cli":
        return CodexCliProvider()
    if kind == "openai-compatible" and endpoint:
        return OpenAICompatibleProvider(endpoint, api_key=os.environ.get("OPENAI_API_KEY"))
    raise ValueError("invalid_provider_selection")

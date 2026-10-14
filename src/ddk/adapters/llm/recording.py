"""Record every model call (audit trail, cost) and replay a recorded session offline.

``RecordingLLMAdapter`` wraps any ``LLMAdapter``. Records never hold prompts or image
bytes, only digests, so they are safe to store next to the case reports. An optional
cassette additionally keeps the model answers so ``ReplayLLMAdapter`` can serve the same
session later without an API key (demos, deterministic tests, bug reports).
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Literal

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models._base import DDKBaseModel

_CASSETTE_VERSION = 1


class CassetteMissError(LookupError):
    """A replayed session has no recorded answer left for this kind of call."""


class LLMCallRecord(DDKBaseModel):
    """One model call, without its prompt text."""

    sequence: int
    purpose: str
    model: str
    status: Literal["ok", "error"]
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    request_digest: str
    response_digest: str | None = None


class RecordingLLMAdapter:
    """Delegates to ``inner`` and keeps a record of each call."""

    def __init__(self, inner: LLMAdapter, *, cassette_path: Path | None = None) -> None:
        self._inner = inner
        self._cassette_path = cassette_path
        self.records: list[LLMCallRecord] = []
        self._answers: list[dict[str, Any]] = []

    @property
    def total_cost_usd(self) -> float:
        return sum(record.cost_usd for record in self.records)

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        return await self._record(messages, config, self._inner.complete(messages, config))

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        return await self._record(
            messages, config, self._inner.complete_structured(messages, config, output_schema)
        )

    def references(self, case_id: str) -> list[str]:
        """Stable references to the recorded calls, for the evidence pack."""
        return [f"llm-call:{case_id}:{record.sequence}" for record in self.records]

    def export(self) -> list[dict[str, Any]]:
        return [record.model_dump(mode="json") for record in self.records]

    def save(self) -> None:
        """Write the cassette (answers included) when a path was given."""
        if self._cassette_path is None:
            return
        self._cassette_path.parent.mkdir(parents=True, exist_ok=True)
        self._cassette_path.write_text(
            json.dumps({"version": _CASSETTE_VERSION, "calls": self._answers}, indent=2) + "\n",
            encoding="utf-8",
        )

    async def _record(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        call: Any,
    ) -> LLMResponse:
        started = time.monotonic()
        purpose = _purpose(messages, config)
        digest = _request_digest(messages, config)
        sequence = len(self.records) + 1
        try:
            response: LLMResponse = await call
        except Exception as exc:
            self.records.append(
                LLMCallRecord(
                    sequence=sequence,
                    purpose=purpose,
                    model=config.model,
                    status="error",
                    error=type(exc).__name__,
                    duration_ms=_elapsed_ms(started),
                    request_digest=digest,
                )
            )
            raise
        self.records.append(
            LLMCallRecord(
                sequence=sequence,
                purpose=purpose,
                model=response.model or config.model,
                status="ok",
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                cost_usd=response.cost_usd,
                duration_ms=_elapsed_ms(started),
                request_digest=digest,
                response_digest=hashlib.sha256(response.content.encode()).hexdigest()[:16],
            )
        )
        self._answers.append(
            {
                "purpose": purpose,
                "model": response.model or config.model,
                "content": response.content,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
            }
        )
        return response


class ReplayLLMAdapter:
    """Serves the answers of a recorded session, per purpose and in recorded order."""

    def __init__(self, calls: list[dict[str, Any]]) -> None:
        self._queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for call in calls:
            self._queues[str(call["purpose"])].append(call)

    @classmethod
    def load(cls, path: Path) -> ReplayLLMAdapter:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls(list(payload.get("calls", [])))

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        purpose = _purpose(messages, config)
        queue = self._queues[purpose]
        if not queue:
            raise CassetteMissError(f"no recorded answer left for purpose {purpose!r}")
        call = queue.popleft()
        return LLMResponse(
            content=str(call["content"]),
            model=str(call.get("model", config.model)),
            input_tokens=int(call.get("input_tokens", 0)),
            output_tokens=int(call.get("output_tokens", 0)),
            cost_usd=0.0,
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        return await self.complete(messages, config)


def _purpose(messages: list[Message], config: LLMCallConfig) -> str:
    explicit = config.metadata.get("purpose")
    if isinstance(explicit, str) and explicit:
        return explicit
    for message in messages:
        if message.role == "system" and message.content.split():
            return message.content.split()[0].lower()
    return "default"


def _request_digest(messages: list[Message], config: LLMCallConfig) -> str:
    canonical = [
        [
            message.role,
            message.content,
            [
                [hashlib.sha256(data.encode()).hexdigest(), media_type]
                for data, media_type in (message.images or [])
            ],
        ]
        for message in messages
    ]
    parts: list[Any] = [canonical, config.model, config.temperature, config.max_tokens]
    if config.effort is not None:  # left out when unset, so earlier recordings keep their digest
        parts.append(config.effort)
    payload = json.dumps(parts, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)

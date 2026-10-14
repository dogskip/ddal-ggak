"""Stand-in for ``anthropic.AsyncAnthropic`` that answers streamed requests with fixed messages."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class _Stream:
    def __init__(self, message: Any) -> None:
        self._message = message

    async def __aenter__(self) -> _Stream:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None

    async def get_final_message(self) -> Any:
        return self._message


class StreamingClient:
    """Records every streamed request; replies in order, repeating the last reply."""

    def __init__(self, *replies: Any) -> None:
        self._replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> _Stream:
        self.requests.append(kwargs)
        index = min(len(self.requests), len(self._replies)) - 1
        return _Stream(self._replies[index])


def reply(
    *blocks: Any,
    stop_reason: str = "end_turn",
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> Any:
    """A provider message with the given content blocks."""

    def dump() -> dict[str, Any]:
        return {}

    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        model_dump=dump,
    )

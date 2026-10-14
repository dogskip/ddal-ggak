"""Bound and validate raw UTF-8 frames before MCP SDK parsing."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import BinaryIO

from anyio import to_thread

from ddk.models.verified_change import MAX_RECORD_BYTES, decode_json


class BoundedStdin(AsyncIterator[str]):
    def __init__(self, stream: BinaryIO) -> None:
        self._stream = stream

    async def __anext__(self) -> str:
        line = await to_thread.run_sync(self._stream.readline, MAX_RECORD_BYTES + 2)
        if not line:
            raise StopAsyncIteration
        payload = line[:-1] if line.endswith(b"\n") else line
        decode_json(payload)
        return line.decode("utf-8", errors="strict")

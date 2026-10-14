"""Readiness uses TCP only and stays within the original check deadline."""

import asyncio
import time

import pytest


async def test_wait_for_preview_accepts_tcp_without_sending_an_http_request():
    from ddk.adapters.verified_worker import wait_for_preview

    received = []
    stopped = asyncio.Event()

    async def connected(reader, writer):
        received.append(await reader.read())
        writer.close()
        await writer.wait_closed()
        stopped.set()

    server = await asyncio.start_server(connected, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        await wait_for_preview(time.monotonic_ns() + 1_000_000_000, port=port)
        await asyncio.wait_for(stopped.wait(), 1)
        assert received == [b""]
    finally:
        server.close()
        await server.wait_closed()


async def test_wait_for_preview_does_not_reset_an_expired_deadline():
    from ddk.adapters.verified_worker import wait_for_preview

    with pytest.raises(ValueError, match="preview_unavailable"):
        await wait_for_preview(time.monotonic_ns() - 1)

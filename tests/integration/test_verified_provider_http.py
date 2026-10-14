from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ddk.adapters.verified_provider import OpenAICompatibleProvider
from tests.unit.adapters.test_verified_provider import request


@pytest.mark.parametrize("cancel", [False, True])
async def test_owned_compatible_http_roundtrip_and_cancel_reap_process(monkeypatch, cancel):
    seen = []
    entered = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            seen.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            entered.set()
            if cancel:
                time.sleep(0.5)
            reply = {
                "model": "model-v1",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                    "prompt_tokens_details": {"cached_tokens": 0},
                },
            }
            body = json.dumps(reply).encode()
            try:
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    import ddk.adapters.verified_provider as module

    original = module.start_owned_process
    children = []

    async def start(*args, **kwargs):
        value = await original(*args, **kwargs)
        children.append(value[0])
        return value

    monkeypatch.setattr(module, "start_owned_process", start)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = OpenAICompatibleProvider(f"http://127.0.0.1:{server.server_port}/v1")
        task = asyncio.create_task(provider(request()))
        if cancel:
            async with asyncio.timeout(5):
                while not entered.is_set():
                    await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert result.usage is not None and result.usage.input_tokens == 2
        assert seen[0]["max_tokens"] == 100 and len(seen) == 1
        assert children and all(child.returncode is not None for child in children)
        for child in children:
            with pytest.raises(ProcessLookupError):
                os.kill(child.pid, 0)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

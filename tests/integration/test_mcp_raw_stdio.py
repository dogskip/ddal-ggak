"""Reject invalid raw frames before the SDK parses or dispatches them."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from ddk.models.verified_change import MAX_RECORD_BYTES

ROOT = Path(__file__).resolve().parents[2]
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "raw-guard-test", "version": "1"},
    },
}
PREFIX = (
    b'{"jsonrpc":"2.0","id":999,"method":"tools/call",'
    b'"params":{"name":"ddk_status","arguments":{'
    b'"run_id":"00000000-0000-4000-8000-000000000055"'
)


def bad_frame(fault):
    if fault == "duplicate":
        return PREFIX + b',"run_id":"00000000-0000-4000-8000-000000000056"}}}\n'
    if fault == "oversized":
        return PREFIX + b"}}}" + b" " * (MAX_RECORD_BYTES + 1) + b"\n"
    if fault == "multibyte_oversized":
        return PREFIX + b',"extra":"' + "한".encode() * 750_000 + b'"}}}\n'
    if fault == "invalid_utf8":
        return PREFIX + b',"extra":"\xff"}}}\n'
    if fault == "depth":
        return PREFIX + b',"extra":' + b"[" * 33 + b"0" + b"]" * 33 + b"}}}\n"
    if fault == "nan":
        return PREFIX + b',"extra":NaN}}}\n'
    raise AssertionError(fault)


@pytest.mark.parametrize(
    "fault", ["duplicate", "oversized", "multibyte_oversized", "invalid_utf8", "depth", "nan"]
)
async def test_bad_raw_frame_closes_transport_without_dispatch(tmp_path, fault):
    env = dict(os.environ)
    env.update(
        PYTHONPATH=os.pathsep.join([str(ROOT / "src"), str(ROOT)]),
        PYTHONDONTWRITEBYTECODE="1",
        DDK_ANTHROPIC_API_KEY="",
        ANTHROPIC_API_KEY="",
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "ddk",
        "serve",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=ROOT,
    )
    assert process.stdin is not None and process.stdout is not None
    try:
        process.stdin.write(json.dumps(INITIALIZE).encode() + b"\n")
        await process.stdin.drain()
        initialized = await asyncio.wait_for(process.stdout.readline(), 5)
        assert json.loads(initialized)["result"]["protocolVersion"] == "2025-11-25"
        payload = b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n' + bad_frame(fault)
        stdout, stderr = await asyncio.wait_for(process.communicate(payload), 8)
        observed = [json.loads(line) for line in stdout.splitlines() if line]
        assert not any(message.get("id") == 999 for message in observed)
        assert process.returncode != 0
        assert all(message["jsonrpc"] == "2.0" for message in observed)
        (tmp_path / "stdout.jsonl").write_bytes(initialized + stdout)
        (tmp_path / "stderr.txt").write_bytes(stderr)
        (tmp_path / "transport.json").write_text(
            json.dumps({"fault": fault, "pid": process.pid, "returncode": process.returncode})
        )
        with pytest.raises(ProcessLookupError):
            os.kill(process.pid, 0)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

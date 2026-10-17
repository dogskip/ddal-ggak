"""Real SDK subprocess transport; injected observations do not prove isolation."""

from __future__ import annotations

import asyncio
import copy
import importlib.metadata
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters, types
from mcp.client import stdio
from mcp.shared.exceptions import McpError

from tests.public_contract import public_payload
from tests.unit.adapters.test_verified_evaluator import request_for
from tests.unit.test_verified_change_engine import RUN_ID
from tests.unit.test_verified_change_engine import scenario as scenario

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = """
import asyncio, os
from pathlib import Path
from ddk import server
from ddk.services.verified_change_service import VerifiedChangeService
from tests.unit.test_verified_change_engine import Evaluator
assert not os.environ.get('DDK_ANTHROPIC_API_KEY')
assert not os.environ.get('ANTHROPIC_API_KEY')
mode = os.environ['DDK_MCP_TEST_MODE']
marker = Path(os.environ['DDK_MCP_TEST_MARKER'])
class Observer(Evaluator):
    async def evaluate(self, request):
        if mode == 'cancel':
            marker.write_text(str(os.getpid()))
            try:
                await asyncio.Event().wait()
            finally:
                marker.with_suffix('.stopped').write_text('stopped')
        return await super().evaluate(request)
observer = Observer(statuses={('candidate', 'target'): 'failed'})
def service(repository):
    return VerifiedChangeService(Path(repository), evaluator=observer)
server._verified_service = service
server.run_server()
"""


class RecordedReceive:
    def __init__(self, stream, chunks):
        self.stream, self.chunks = stream, chunks

    async def receive(self, max_bytes=65536):
        chunk = await self.stream.receive(max_bytes)
        self.chunks.append(chunk)
        return chunk

    async def aclose(self):
        await self.stream.aclose()


class RecordedSend:
    def __init__(self, stream, chunks):
        self.stream, self.chunks = stream, chunks

    async def send(self, item):
        await self.stream.send(item)
        self.chunks.append(item)

    async def aclose(self):
        await self.stream.aclose()


class RecordedProcess:
    def __init__(self, process, incoming, outgoing):
        self.process = process
        self.stdout = RecordedReceive(process.stdout, incoming)
        self.stdin = RecordedSend(process.stdin, outgoing)

    def __getattr__(self, name):
        return getattr(self.process, name)

    async def __aenter__(self):
        await self.process.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.process.__aexit__(*args)


def messages(chunks):
    return [json.loads(line) for line in b"".join(chunks).splitlines() if line]


@asynccontextmanager
async def connected(tmp_path, monkeypatch, *, mode="default"):
    incoming, outgoing, processes = [], [], []
    original = stdio._create_platform_compatible_process

    async def create(**kwargs):
        process = await original(**kwargs)
        processes.append(process)
        return RecordedProcess(process, incoming, outgoing)

    monkeypatch.setattr(stdio, "_create_platform_compatible_process", create)
    env = {
        "PYTHONPATH": os.pathsep.join([str(ROOT / "src"), str(ROOT)]),
        "PYTHONDONTWRITEBYTECODE": "1",
        "DDK_ANTHROPIC_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "DDK_MCP_TEST_MODE": mode,
        "DDK_MCP_TEST_MARKER": str(tmp_path / "entered"),
    }
    args = ["-m", "ddk", "serve"] if mode == "default" else ["-c", BOOTSTRAP]
    params = StdioServerParameters(command=sys.executable, args=args, cwd=ROOT, env=env)
    try:
        with (tmp_path / "stderr.txt").open("w") as errors:
            async with stdio.stdio_client(params, errlog=errors) as (read, write):
                async with ClientSession(read, write, timedelta(seconds=15)) as session:
                    initialized = await session.initialize()
                    assert initialized.protocolVersion == "2025-11-25"
                    yield session, outgoing
    finally:
        (tmp_path / "stdout.jsonl").write_bytes(b"".join(incoming))
        (tmp_path / "stdin.jsonl").write_bytes(b"".join(outgoing))
        observed = messages(incoming)
        assert observed and all(item["jsonrpc"] == "2.0" for item in observed)
        for process in processes:
            assert process.returncode is not None
            with pytest.raises(ProcessLookupError):
                os.kill(process.pid, 0)
        (tmp_path / "transport.json").write_text(
            json.dumps(
                {
                    "sdk": importlib.metadata.version("mcp"),
                    "negotiated": "2025-11-25",
                    "mode": mode,
                    "stdout_messages": len(observed),
                    "stdout_jsonrpc_only": True,
                    "processes": [
                        {"pid": process.pid, "returncode": process.returncode}
                        for process in processes
                    ],
                },
                indent=2,
            )
        )


def request(scenario):
    store, case, baseline, candidate = scenario
    return {
        "repository": str(store.repository),
        "case_id": case["case_id"],
        "baseline": str(baseline),
        "candidate": str(candidate),
        "run_id": RUN_ID,
        "change_requirements": {"src/App.tsx": ["R2"]},
    }


def content(result):
    assert result.content[0].type == "text"
    return public_payload(result.content[0].text)


async def test_actual_cli_stdio_lists_existing_tools_and_reports_errors(tmp_path, monkeypatch):
    async with connected(tmp_path, monkeypatch) as (session, _):
        tools = {tool.name: tool for tool in (await session.list_tools()).tools}
        assert set(tools) == {
            "ddk_design_new",
            "design_new",
            "ddk_preflight",
            "preflight",
            "ddk_version",
            "ddk_verify",
            "ddk_status",
            "ddk_doctor",
            "ddk_init",
            "ddk_repair",
            "ddk_apply",
            "ddk_probe",
            "ddk_query_ledger",
            "ddk_gate_status",
            "ddk_read_evidence",
            "ddk_replay",
        }
        for name in ("ddk_verify", "ddk_gate_status", "ddk_read_evidence", "ddk_replay"):
            assert tools[name].inputSchema["additionalProperties"] is False
        assert not (await session.call_tool("ddk_version")).isError
        unknown = await session.call_tool("unknown")
        assert unknown.isError
        invalid = await session.call_tool("ddk_verify", {"trusted_local_approved": True})
        assert invalid.isError and "invalid_tool_input" in invalid.content[0].text
        absent = await session.call_tool(
            "ddk_status", {"run_id": RUN_ID, "repository": str(tmp_path / "repository")}
        )
        assert absent.isError and "record_not_found" in absent.content[0].text
        assert not (tmp_path / "repository").exists()


async def test_real_service_check_failure_repeat_conflict_and_status(
    tmp_path, monkeypatch, scenario
):
    async with connected(tmp_path, monkeypatch, mode="observe") as (session, _):
        args = request(scenario)
        result = await session.call_tool("ddk_verify", args)
        assert not result.isError
        record = content(result)
        assert record["decision"] == "blocked" and record["model_calls"] == []
        assert record["actions"][0]["code"] == "required_check_failed"
        repeat = await session.call_tool("ddk_verify", args)
        assert not repeat.isError and content(repeat) == record
        status = await session.call_tool(
            "ddk_status", {"run_id": RUN_ID, "repository": args["repository"]}
        )
        assert not status.isError and content(status) == record
        scenario[3].joinpath("src/App.tsx").write_bytes(b"different")
        conflict = await session.call_tool("ddk_verify", args)
        assert conflict.isError and "request_conflict" in conflict.content[0].text
        after_conflict = await session.call_tool(
            "ddk_status", {"run_id": RUN_ID, "repository": args["repository"]}
        )
        assert not after_conflict.isError and content(after_conflict) == record


async def test_stdio_cannot_authorize_a_trusted_local_case(tmp_path, monkeypatch, scenario):
    store, case, _, _ = scenario
    local_case = copy.deepcopy(case)
    local_case.update(
        case_id="00000000-0000-4000-8000-000000000060", assurance_required="trusted-local"
    )
    payloads = {
        item["path"]: (
            store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    store.publish_case(local_case, payloads)
    async with connected(tmp_path, monkeypatch) as (session, _):
        args = request(scenario) | {"case_id": local_case["case_id"]}
        denied = await session.call_tool("ddk_verify", args)
        assert denied.isError
        assert "trusted_local_confirmation_required" in denied.content[0].text
        escalation = await session.call_tool("ddk_verify", args | {"trusted_local_approved": True})
        assert escalation.isError and "invalid_tool_input" in escalation.content[0].text
        assert not store.path_for("run", RUN_ID).exists()


async def test_default_isolation_unavailable_is_error_and_saved_status(
    tmp_path, monkeypatch, scenario
):
    store, case, _, _ = scenario
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    marker = tmp_path / "host-executed"
    execution, baseline, _ = request_for(
        runtime,
        argv=["node", "-e", f"require('fs').writeFileSync({str(marker)!r}, 'unsafe')"],
        plan_changes={"preview_argv": ["node", "serve.js", "{port}"]},
        env_changes={"assurance": "isolated"},
    )
    candidate = runtime / "candidate"
    candidate.mkdir()
    candidate.joinpath("index.html").write_bytes(b"<h1>Candidate</h1>")
    candidate.joinpath("index.html").chmod(0o644)
    source = execution.snapshot.files[0]
    fixed = execution.frozen_inputs
    definition = copy.deepcopy(case)
    definition.update(
        case_id="00000000-0000-4000-8000-000000000061",
        scope_paths=[source.path],
        baseline_tree_sha256=execution.snapshot.tree_sha256,
        environment_sha256=execution.environment_sha256,
        evaluator_sha256=execution.evaluator_sha256,
        inputs=[
            source.manifest_entry() | {"role": "source"},
            *[
                item.manifest_entry()
                | {"role": "criteria" if item.path.startswith("criteria/") else "environment"}
                for item in fixed
            ],
        ],
        requirements=[
            {
                "requirement_id": "R1",
                "description": "preserve command behavior",
                "required": True,
                "check_ids": [execution.checks[0]["check_id"], "preserve", "target"],
            }
        ],
        checks=[
            *execution.checks,
            *[
                execution.checks[0]
                | {
                    "check_id": role,
                    "role": role,
                    "kind": "browser",
                    "command_argv": [],
                    "viewport": {"width": 1280, "height": 800},
                }
                for role in ("preserve", "target")
            ],
        ],
    )
    store.publish_case(
        definition, {item.path: item.content for item in [source, *execution.frozen_inputs]}
    )
    async with connected(tmp_path, monkeypatch) as (session, _):
        args = {
            "repository": str(store.repository),
            "case_id": definition["case_id"],
            "baseline": str(baseline),
            "candidate": str(candidate),
            "run_id": RUN_ID,
            "change_requirements": {source.path: ["R1"]},
        }
        unavailable = await session.call_tool("ddk_verify", args)
        assert unavailable.isError
        assert "isolation_unavailable" in unavailable.content[0].text
        status = await session.call_tool(
            "ddk_status", {"run_id": RUN_ID, "repository": str(store.repository)}
        )
        assert not status.isError
        record = content(status)
        assert record["decision"] == "blocked" and record["model_calls"] == []
        assert record["actions"][0]["code"] == "isolation_unavailable"
        assert not marker.exists()
        assert baseline.joinpath("index.html").read_bytes() == source.content
        assert candidate.joinpath("index.html").read_bytes() == b"<h1>Candidate</h1>"


async def test_cancel_notification_preserves_owned_run_and_closes_process(
    tmp_path, monkeypatch, scenario
):
    async with connected(tmp_path, monkeypatch, mode="cancel") as (session, outgoing):
        args = request(scenario)
        call = asyncio.create_task(session.call_tool("ddk_verify", args))
        try:
            async with asyncio.timeout(10):
                while not (tmp_path / "entered").exists():
                    await asyncio.sleep(0.01)
            wire_call = next(
                item for item in reversed(messages(outgoing)) if item.get("method") == "tools/call"
            )
            await session.send_notification(
                types.ClientNotification(
                    types.CancelledNotification(
                        params=types.CancelledNotificationParams(requestId=wire_call["id"])
                    )
                )
            )
            with pytest.raises(McpError, match="Request cancelled"):
                await call
            async with asyncio.timeout(5):
                while True:
                    status = await session.call_tool(
                        "ddk_status", {"run_id": RUN_ID, "repository": args["repository"]}
                    )
                    assert not status.isError
                    record = content(status)
                    if record["status"] == "cancelled":
                        break
                    await asyncio.sleep(0.02)
            assert record["decision"] is None and record["model_calls"] == []
            assert (tmp_path / "entered.stopped").read_text() == "stopped"
        finally:
            if not call.done():
                call.cancel()
                await asyncio.gather(call, return_exceptions=True)

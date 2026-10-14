"""Strict MCP input and service forwarding checks without a model call."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from ddk import server

CASE_ID = "00000000-0000-4000-8000-000000000001"
RUN_ID = "00000000-0000-4000-8000-000000000055"


def arguments():
    return {
        "repository": "/repository",
        "case_id": CASE_ID,
        "baseline": "/baseline",
        "candidate": "/candidate",
        "run_id": RUN_ID,
        "project_inputs": {"package.json": "/inputs/package.json"},
        "change_requirements": {"src/App.tsx": ["R2"]},
    }


def definition(schema, node):
    while "$ref" in node:
        node = schema["$defs"][node["$ref"].split("/")[-1]]
    return node


@pytest.fixture
def service(monkeypatch):
    value = Mock()
    value.verify = AsyncMock(return_value={"run_id": RUN_ID, "decision": "blocked", "actions": []})
    value.status.return_value = {"run_id": RUN_ID, "status": "completed"}
    factory = Mock(return_value=value)
    monkeypatch.setattr(server, "_verified_service", factory, raising=False)
    return factory, value


async def test_verified_tools_expose_bounded_input_and_accurate_annotations():
    tools = {tool.name: tool for tool in await server.mcp.list_tools()}
    for name in ("ddk_verify", "ddk_status"):
        tool = tools[name]
        schema = tool.inputSchema
        assert schema["additionalProperties"] is False
        assert definition(schema, schema["properties"]["run_id"])["maxLength"] == 36
        assert "trusted_local_approved" not in schema["properties"]
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.destructiveHint is False
        assert tool.annotations.openWorldHint is False
    assert tools["ddk_verify"].annotations.readOnlyHint is False
    assert tools["ddk_status"].annotations.readOnlyHint is True
    schema = tools["ddk_verify"].inputSchema
    assert definition(schema, schema["properties"]["baseline"])["maxLength"] == 4096
    mappings = definition(schema, schema["properties"]["change_requirements"]["anyOf"][0])
    assert mappings["maxProperties"] == 20
    assert mappings["additionalProperties"]["maxItems"] == 256


async def test_verify_uses_shared_service_without_host_permission(service):
    factory, value = service
    result = await server.mcp.call_tool("ddk_verify", arguments())
    assert json.loads(result[0].text)["decision"] == "blocked"
    factory.assert_called_once_with("/repository")
    value.verify.assert_awaited_once_with(
        CASE_ID,
        baseline=Path("/baseline"),
        candidate=Path("/candidate"),
        run_id=RUN_ID,
        project_inputs={"package.json": "/inputs/package.json"},
        change_requirements={"src/App.tsx": ["R2"]},
        trusted_local_approved=False,
    )


async def test_status_uses_shared_service(service):
    factory, value = service
    result = await server.mcp.call_tool("ddk_status", {"run_id": RUN_ID})
    assert json.loads(result[0].text)["status"] == "completed"
    factory.assert_called_once_with(".")
    value.status.assert_called_once_with(RUN_ID)


@pytest.mark.parametrize(
    "change",
    [
        {"trusted_local_approved": True},
        {"run_id": "not-a-uuid"},
        {"run_id": 1},
        {"case_id": "not-a-uuid"},
        {"baseline": ""},
        {"candidate": "a" * 4097},
        {"repository": False},
        {"project_inputs": '{"package.json":"/input"}'},
        {"project_inputs": {"": "/input"}},
        {"project_inputs": {"package.json": 1}},
        {"change_requirements": {"src/App.tsx": "R2"}},
        {"change_requirements": {"src/App.tsx": []}},
        {"change_requirements": {"src/App.tsx": [1]}},
        {"change_requirements": {"src/App.tsx": ["R2"] * 257}},
        {"change_requirements": {f"{index}.tsx": ["R2"] for index in range(21)}},
        {"project_inputs": {str(index): "/input" for index in range(257)}},
    ],
)
async def test_invalid_arguments_are_tool_errors_before_service(service, change):
    request = arguments() | change
    with pytest.raises(ToolError, match="invalid_tool_input"):
        await server.mcp.call_tool("ddk_verify", request)
    service[0].assert_not_called()


async def test_total_request_bytes_are_bounded_before_service(service):
    request = arguments() | {"project_inputs": {str(index): "한" * 4096 for index in range(200)}}
    with pytest.raises(ToolError, match="request_size_limit"):
        await server.mcp.call_tool("ddk_verify", request)
    service[0].assert_not_called()


@pytest.mark.parametrize("code", ["isolation_unavailable", "environment_gap"])
async def test_unavailable_execution_is_tool_error_with_queryable_run(service, code):
    service[1].verify.return_value["actions"] = [{"code": code}]
    with pytest.raises(ToolError, match=f"{code}.*{RUN_ID}.*ddk_status"):
        await server.mcp.call_tool("ddk_verify", arguments())


@pytest.mark.parametrize("operation", ["ddk_verify", "ddk_status"])
async def test_service_errors_do_not_expose_input_values(service, operation):
    error = ValueError("invalid_json: secret=private-value\n" + "x" * 2000)
    if operation == "ddk_verify":
        service[1].verify.side_effect = error
        request = arguments()
    else:
        service[1].status.side_effect = error
        request = {"run_id": RUN_ID}
    with pytest.raises(ToolError) as caught:
        await server.mcp.call_tool(operation, request)
    assert "invalid_json" in str(caught.value)
    assert "private-value" not in str(caught.value)
    assert len(str(caught.value)) < 300


async def test_cancellation_reaches_the_service_and_is_not_normalized(service):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def verify(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    service[1].verify.side_effect = verify
    task = asyncio.create_task(server.mcp.call_tool("ddk_verify", arguments()))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()

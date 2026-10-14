from __future__ import annotations

import pytest
from mcp.server.fastmcp.exceptions import ToolError

from ddk.server import mcp


async def test_oneclick_tools_reject_extra_properties_and_ownerless_mutations(monkeypatch):
    monkeypatch.delenv("DDK_MCP_CAPABILITIES", raising=False)
    tools = {t.name: t for t in await mcp.list_tools()}
    names = {
        "ddk_doctor",
        "ddk_init",
        "ddk_verify",
        "ddk_repair",
        "ddk_status",
        "ddk_probe",
        "ddk_apply",
        "ddk_query_ledger",
    }
    assert names <= set(tools)
    assert all(tools[n].inputSchema["additionalProperties"] is False for n in names)
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "ddk_apply", {"run_id": "00000000-0000-4000-8000-000000000001", "approved": True}
        )
    with pytest.raises(ToolError):
        await mcp.call_tool("ddk_doctor", {"extra": "invalid"})


async def test_mcp_repair_cannot_redirect_owner_provider_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("DDK_MCP_CAPABILITIES", "repair")
    monkeypatch.setenv("DDK_MCP_REPOSITORY", str(tmp_path))
    monkeypatch.setenv("DDK_MCP_PROVIDER_ENDPOINT", "https://approved.example/v1")
    args = {
        "source_run_id": "00000000-0000-4000-8000-000000000001",
        "run_id": "00000000-0000-4000-8000-000000000002",
        "baseline": str(tmp_path),
        "candidate": str(tmp_path),
        "repository": str(tmp_path),
        "approved": True,
        "provider": "openai-compatible",
        "endpoint": "https://unapproved.example/v1",
    }
    with pytest.raises(ToolError, match="provider_endpoint_not_granted"):
        await mcp.call_tool("ddk_repair", args)

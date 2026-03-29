"""Unit tests for the MCP server surface."""

from __future__ import annotations

from unittest.mock import patch

import anyio

from ddk.server import mcp, run_server


async def _list_tool_names() -> list[str]:
    tools = await mcp.list_tools()
    return sorted(tool.name for tool in tools)


def test_mcp_server_registers_expected_tools() -> None:
    tool_names = anyio.run(_list_tool_names)

    assert tool_names == ["ddk_version", "design_new", "preflight"]


def test_run_server_delegates_to_fastmcp() -> None:
    with patch("ddk.server.mcp.run") as run_mock:
        run_server()

    run_mock.assert_called_once_with()

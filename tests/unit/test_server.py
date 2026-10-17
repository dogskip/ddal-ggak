"""Unit tests for the MCP server surface."""

from __future__ import annotations

import json
from unittest.mock import patch

import anyio

from ddk.server import ddk_version, mcp, preflight, run_server


async def _list_tool_names() -> list[str]:
    tools = await mcp.list_tools()
    return sorted(tool.name for tool in tools)


def test_mcp_server_registers_expected_tools() -> None:
    tool_names = anyio.run(_list_tool_names)

    assert tool_names == sorted(
        [
            "ddk_status",
            "ddk_verify",
            "ddk_version",
            "ddk_design_new",
            "design_new",
            "ddk_preflight",
            "preflight",
            "ddk_doctor",
            "ddk_init",
            "ddk_repair",
            "ddk_apply",
            "ddk_probe",
            "ddk_query_ledger",
            "ddk_gate_status",
            "ddk_read_evidence",
            "ddk_replay",
        ]
    )


def test_run_server_delegates_to_fastmcp() -> None:
    with patch("ddk.server.mcp.run") as run_mock:
        run_server()

    run_mock.assert_called_once_with()


def test_preflight_returns_json_with_checks() -> None:
    result = preflight()
    data = json.loads(result)

    assert "all_ok" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)
    assert len(data["checks"]) >= 2

    check_names = [c["check"] for c in data["checks"]]
    assert "Python >= 3.12" in check_names
    assert "DDK_ANTHROPIC_API_KEY" in check_names
    assert "anthropic SDK" in check_names


def test_preflight_python_version_passes() -> None:
    data = json.loads(preflight())
    py_check = next(c for c in data["checks"] if c["check"] == "Python >= 3.12")
    assert py_check["ok"] is True


def test_preflight_anthropic_sdk_installed() -> None:
    data = json.loads(preflight())
    sdk_check = next(c for c in data["checks"] if c["check"] == "anthropic SDK")
    assert sdk_check["ok"] is True
    assert sdk_check["detail"] == "installed"


def test_ddk_version_returns_string() -> None:
    v = ddk_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_ddk_version_fallback_on_error() -> None:
    with patch("importlib.metadata.version", side_effect=Exception("not found")):
        v = ddk_version()
    assert v == "0.0.0-dev"


def test_design_new_no_api_key() -> None:
    async def _run() -> str:
        from ddk.server import design_new

        with patch("ddk.models.config.DdalggakConfig") as mock_cfg_cls:
            mock_cfg = mock_cfg_cls.return_value
            mock_cfg.anthropic_api_key = ""
            return await design_new(idea="test project")

    result = anyio.run(_run)
    data = json.loads(result)
    assert data["success"] is False
    assert "ANTHROPIC_API_KEY" in data["error"]

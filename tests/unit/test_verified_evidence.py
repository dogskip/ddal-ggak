from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from ddk.services.verified_evidence import read_evidence
from tests.unit.test_verified_change_engine import Evaluator, verify
from tests.unit.test_verified_change_engine import scenario as scenario


async def diagnostic_run(scenario, raw):
    observer = Evaluator(
        metadata=lambda outcome: replace(
            outcome, artifacts=tuple(replace(a, content=raw) for a in outcome.artifacts)
        )
    )
    return await verify(scenario, observer)


async def test_evidence_hashes_full_raw_then_redacts_before_range_selection(scenario):
    raw = (
        "safe prefix\\nAuthorization: Bearer sk-" + "a" * 48 + "\\nAssertionError: missing banner"
    ).encode()
    run = await diagnostic_run(scenario, raw)
    artifact = next(a for a in run["artifacts"] if a["kind"] == "log")
    result = read_evidence(scenario[0], run["run_id"], artifact["artifact_id"], offset=0, limit=100)
    assert "sk-" + "a" * 48 not in result["content"]
    assert result["raw_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["execution_repeated"] is False
    assert result["next_offset"] <= 100
    assert scenario[0].run(run["run_id"]) == run


async def test_evidence_rejects_sources_and_tampered_diagnostics(scenario):
    run = await diagnostic_run(scenario, b"AssertionError: test evidence")
    store = scenario[0]
    source = next(a for a in run["artifacts"] if a["kind"] == "source")
    with pytest.raises(ValueError, match="evidence_not_diagnostic"):
        read_evidence(store, run["run_id"], source["artifact_id"])
    diagnostic = next(a for a in run["artifacts"] if a["kind"] == "log")
    (store.path_for("run", run["run_id"]) / diagnostic["path"]).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        read_evidence(store, run["run_id"], diagnostic["artifact_id"])


async def test_private_evidence_mcp_requires_owner_grant_even_when_read_only(tmp_path, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    from ddk.server import mcp

    names = {t.name: t for t in await mcp.list_tools()}
    assert names["ddk_read_evidence"].inputSchema["additionalProperties"] is False
    monkeypatch.delenv("DDK_MCP_CAPABILITIES", raising=False)
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "ddk_read_evidence",
            {
                "run_id": "00000000-0000-4000-8000-000000000099",
                "artifact_id": "a",
                "repository": str(tmp_path),
                "approved": True,
            },
        )

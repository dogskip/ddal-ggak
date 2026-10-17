"""Public JSON remains parseable on success, use errors and missing records."""

from __future__ import annotations

import json

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from ddk.cli import app


def json_commands():
    def walk(command, path):
        if any("--json" in getattr(p, "opts", []) for p in command.params):
            yield path
        for name, child in getattr(command, "commands", {}).items():
            yield from walk(child, [*path, name])

    return list(walk(get_command(app), []))


@pytest.mark.parametrize("command", json_commands(), ids=lambda p: " ".join(p))
def test_every_json_command_reports_usage_errors_as_one_envelope(command, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, [*command, "--json", "--nonexistent-option"])
    assert result.exit_code == 2, result.output
    payload = json.loads(result.stdout)
    assert set(payload) == {"schema_version", "command", "status", "data", "error", "actions"}
    assert payload["schema_version"] == "ddk/2"
    assert payload["command"] == " ".join(command)
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "usage_error"


def test_status_without_a_case_is_structured_and_blocked(tmp_path):
    result = CliRunner().invoke(app, ["status", "--repo", str(tmp_path), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "ddk/2"
    assert payload["status"] == "blocked"
    assert payload["error"]["code"] == "case_not_found"


def test_bad_settings_and_missing_key_have_configuration_exit(tmp_path):
    for env in [
        {"DDK_COST_CAP_USD": "broken"},
        {"DDK_ANTHROPIC_API_KEY": "", "ANTHROPIC_API_KEY": ""},
    ]:
        result = CliRunner().invoke(
            app, ["run", "absent.png", "--repo", str(tmp_path), "--json"], env=env
        )
        assert result.exit_code == 3, result.output
        payload = json.loads(result.stdout)
        assert payload["status"] == "error"
        assert payload["error"]["code"] in {"invalid_settings", "api_key_required"}


def test_install_and_uninstall_success_contract(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for args in [["install", "--host", "gemini"], ["uninstall", "--host", "gemini"]]:
        result = CliRunner().invoke(app, [*args, "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "ddk/2"
        assert payload["status"] == "ok"
        assert payload["error"] is None
    assert list(tmp_path.iterdir()) == []


async def test_all_mcp_tools_use_the_same_contract_before_and_after_validation(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.exceptions import ToolError
    from mcp.types import TextContent

    from ddk.server import mcp

    def sample(schema, root):
        if "$ref" in schema:
            return sample(root["$defs"][schema["$ref"].rsplit("/", 1)[-1]], root)
        if "anyOf" in schema:
            return sample(next(s for s in schema["anyOf"] if s.get("type") != "null"), root)
        if "enum" in schema:
            return schema["enum"][0]
        if "const" in schema:
            return schema["const"]
        kind = schema.get("type")
        if kind == "object":
            return {
                key: sample(schema["properties"][key], root) for key in schema.get("required", [])
            }
        if kind == "array":
            return [sample(schema["items"], root) for _ in range(schema.get("minItems", 0))]
        if kind == "boolean":
            return False
        if kind in {"integer", "number"}:
            return schema.get("minimum", 1)
        if schema.get("maxLength") == 36:
            return "00000000-0000-4000-8000-000000000001"
        return "x" * max(1, schema.get("minLength", 1))

    called = []

    async def native_result(self, name, arguments):
        called.append(name)
        data = {"status": "ready", "decision": "ready", "actions": []}
        if name == "ddk_gate_status":
            data = {"gate_status": "passed"}
        elif name == "ddk_replay":
            data = {"evidence_integrity": True}
        elif name == "preflight":
            data = {"all_ok": True}
        elif name == "design_new":
            data = {"success": True}
        text = "test-version" if name == "ddk_version" else json.dumps(data)
        return [TextContent(type="text", text=text)]

    monkeypatch.setattr(FastMCP, "call_tool", native_result)
    tools = await mcp.list_tools()
    assert len(tools) == 14
    for tool in tools:
        args = sample(tool.inputSchema, tool.inputSchema)
        result = await mcp.call_tool(tool.name, args)
        payload = json.loads(result[0].text)
        assert payload["schema_version"] == "ddk/2"
        assert payload["command"] == tool.name
        assert payload["status"] == "ok"
        assert payload["error"] is None
        count = len(called)
        with pytest.raises(ToolError) as caught:
            await mcp.call_tool(tool.name, {**args, "unrecognized": True})
        failure = json.loads(str(caught.value))
        assert failure["schema_version"] == "ddk/2"
        assert failure["error"]["code"] == "invalid_tool_input"
        assert len(called) == count


def test_generated_exit_docs_are_current():
    from pathlib import Path

    from scripts.generate_exit_codes import render

    root = Path(__file__).resolve().parents[2] / "docs"
    assert (root / "EXIT-CODES.md").read_text() == render("en")
    assert (root / "EXIT-CODES.ko.md").read_text() == render("ko")


@pytest.mark.parametrize(
    "command",
    [
        ["init"],
        ["change", "init"],
        ["up"],
        ["probe"],
        ["change", "reindex"],
        ["change", "evidence"],
        ["change", "gate"],
        ["change", "replay"],
        ["proof"],
        ["audit"],
    ],
)
def test_successful_service_results_reach_the_actual_cli_contract(command, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    ready = {"status": "ready", "actions": []}
    identifier = "00000000-0000-4000-8000-000000000001"
    arguments = [*command, "--repo", str(tmp_path), "--json"]
    name = " ".join(command)
    if name in {"init", "change init"}:
        monkeypatch.setattr(
            "ddk.services.case_bootstrapper.CaseBootstrapper.initialize",
            AsyncMock(return_value={**ready, "dry_run": True}),
        )
        arguments += ["--dry-run"]
    elif name == "up":
        monkeypatch.setattr(
            "ddk.services.verified_up.up", AsyncMock(return_value={**ready, "dry_run": True})
        )
        arguments += ["--dry-run"]
    elif name == "probe":
        monkeypatch.setattr("ddk.cli.probe.capture_preview_probe", AsyncMock(return_value=ready))
        arguments += ["--url", "https://example.invalid"]
    elif name == "change reindex":
        monkeypatch.setattr(
            "ddk.services.verified_index.VerifiedIndexCatalog.reindex_all", lambda self: ready
        )
    elif name == "change evidence":
        monkeypatch.setattr(
            "ddk.services.verified_evidence.read_evidence",
            lambda *a, **kw: {"content": "bounded", "run_id": identifier},
        )
        arguments += ["--run-id", identifier, "--artifact-id", "diagnostic", "--limit", "128"]
    elif name == "change gate":
        monkeypatch.setattr(
            "ddk.services.verified_gate.gate_status", lambda *a, **kw: {"gate_status": "passed"}
        )
    elif name == "change replay":
        monkeypatch.setattr(
            "ddk.services.verified_replay.replay_run", lambda *a, **kw: {"evidence_integrity": True}
        )
        arguments += ["--run-id", identifier]
    elif name == "proof":
        monkeypatch.setattr(
            "ddk.services.proof_ledger.ProofLedger.verify",
            lambda self: SimpleNamespace(model_dump=lambda **kw: {"allowed_claims": []}),
        )
    elif name == "audit":
        monkeypatch.setattr(
            "ddk.services.compliance_auditor.ComplianceAuditor.audit",
            lambda self: SimpleNamespace(model_dump=lambda **kw: {"gaps": []}),
        )
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "ddk/2"
    assert payload["command"] == name
    assert payload["status"] == "ok"
    assert payload["error"] is None


def test_ready_image_fixture_serializes_run_status_certify_and_apply(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from ddk.models.evidence import EvidencePack
    from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
    from ddk.models.release import ReleaseDecision
    from ddk.models.scorecard import Scorecard
    from tests.fakes.images import write_png
    from tests.fakes.runtime_services import stub_runtime_services

    image = write_png(tmp_path / "design.png")
    state = {
        "case_id": "C-001",
        "release_decision": ReleaseDecision(case_id="C-001", decision="ready"),
        "scorecard": Scorecard(
            case_id="C-001",
            precision=1,
            maintainability=1,
            automation=1,
            scalability=1,
            overall=1,
            grade="A",
        ),
        "evidence_pack": EvidencePack(case_id="C-001", terminal_state="ready"),
        "generated_artifacts": GeneratedArtifactSet(
            case_id="C-001",
            files=[
                GeneratedFile(
                    path="src/Card.tsx", content="card\n", source_node_id="n", is_new=True
                )
            ],
        ),
        "fix_attempts": [],
    }
    monkeypatch.setattr(
        "ddk.cli.delivery.build_runtime_services", lambda cfg: stub_runtime_services()
    )
    monkeypatch.setattr(
        "ddk.services.pipeline_runner.PipelineRunner.run_case", AsyncMock(return_value=state)
    )
    for command in [
        ["run", str(image), "--no-visual"],
        ["status"],
        ["certify"],
        ["apply", "--dry-run"],
    ]:
        result = CliRunner().invoke(app, [*command, "--repo", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == "ddk/2"
        assert payload["command"] == command[0]
        assert payload["status"] == "ok"
        assert payload["error"] is None
    assert not (tmp_path / "src/Card.tsx").exists()

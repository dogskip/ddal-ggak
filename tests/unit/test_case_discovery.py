from __future__ import annotations

import hashlib
import json
import tomllib

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.services.case_bootstrapper import CaseBootstrapper
from tests.unit.adapters.test_verified_browser import environment
from tests.unit.test_case_bootstrapper import setup_repo


def valid_draft():
    return """draft = true
scope_paths = ["index.html"]
preview_argv = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
[[checks]]
check_id = "target"
role = "target"
steps = [{action = "expect-text", selector = "h1", value = "After"}]
[[checks]]
check_id = "preserve"
role = "preserve"
steps = [{action = "expect-visible", selector = "body"}]
"""


async def test_discover_detects_native_reports_without_executing_scripts(tmp_path):
    marker = tmp_path / "executed"
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "build": "vite build",
                    "lint": "eslint .",
                    "typecheck": "tsc --noEmit",
                    "test": "vitest run",
                    "dev": "touch executed && vite",
                }
            }
        )
    )
    result = await CaseBootstrapper(tmp_path).discover()
    assert result["status"] == "draft" and result["execution_approved"] is False
    config = tomllib.loads((tmp_path / ".ddk/verify.draft.toml").read_text())
    assert config["draft"] is True and not marker.exists()
    assert not (tmp_path / ".ddk/verify.toml").exists()
    tests = [c for c in config["checks"] if c["kind"] == "test"]
    assert tests[0]["report_adapter"] == "vitest-json"
    assert "{report}" in " ".join(tests[0]["command_argv"])
    assert all(c["role"] != "target" for c in config["checks"])
    blocked = await CaseBootstrapper(tmp_path).initialize("Fix login", dry_run=True)
    assert blocked["actions"][0]["code"] == "draft_criteria_unapproved"


async def test_discover_python_uses_junit_and_dry_run_has_no_writes(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n[tool.ruff]\nline-length=100\n"
    )
    result = await CaseBootstrapper(tmp_path).discover(dry_run=True)
    assert result["draft"] is True and result["dry_run"] is True
    check = next(c for c in result["checks"] if c["kind"] == "test")
    assert check["report_adapter"] == "junit-xml"
    assert "--junitxml={report}" in check["command_argv"]
    assert not (tmp_path / ".ddk").exists()


async def test_discover_preview_command_needs_separate_execution_confirmation(tmp_path):
    with pytest.raises(ValueError, match="preview_execution_confirmation_required"):
        await CaseBootstrapper(tmp_path).discover("python3 -m http.server {port}")
    assert not (tmp_path / ".ddk").exists()


async def test_draft_flag_blocks_even_complete_independent_definitions(tmp_path):
    config = tomllib.loads(valid_draft())
    result = await CaseBootstrapper(tmp_path).initialize(
        "Fix heading", configuration=config, dry_run=True
    )
    assert result["status"] == "blocked"
    assert result["actions"][0]["code"] == "draft_criteria_unapproved"
    assert not (tmp_path / ".ddk").exists()


async def test_discover_requires_explicit_target_before_approval(tmp_path):
    await CaseBootstrapper(tmp_path).discover()
    result = CaseBootstrapper(tmp_path).approve_draft()
    assert result["status"] == "blocked"
    assert result["actions"][0]["code"] == "acceptance_checks_required"
    assert not (tmp_path / ".ddk/verify.toml").exists()


def test_approve_copies_reviewed_bytes_without_overwriting_existing_configuration(tmp_path):
    folder = tmp_path / ".ddk"
    folder.mkdir()
    draft = folder / "verify.draft.toml"
    draft.write_text(valid_draft())
    original = draft.read_bytes()
    result = CaseBootstrapper(tmp_path).approve_draft()
    assert result["status"] == "approved"
    approved = tomllib.loads((folder / "verify.toml").read_text())
    assert approved["draft"] is False
    assert draft.read_bytes() == original
    assert result["draft_sha256"] == hashlib.sha256(original).hexdigest()
    before = (folder / "verify.toml").read_bytes()
    with pytest.raises(FileExistsError):
        CaseBootstrapper(tmp_path).approve_draft()
    assert (folder / "verify.toml").read_bytes() == before


def test_approve_rejects_symlink_and_dry_run_never_publishes(tmp_path):
    folder = tmp_path / ".ddk"
    folder.mkdir()
    source = tmp_path / "outside.toml"
    source.write_text(valid_draft())
    (folder / "verify.draft.toml").symlink_to(source)
    with pytest.raises((ValueError, OSError)):
        CaseBootstrapper(tmp_path).approve_draft()
    assert source.read_text() == valid_draft()
    (folder / "verify.draft.toml").unlink()
    (folder / "verify.draft.toml").write_text(valid_draft())
    result = CaseBootstrapper(tmp_path).approve_draft(dry_run=True)
    assert result["dry_run"] and not (folder / "verify.toml").exists()


async def test_bootstrap_seals_configuration_selection_and_absence(tmp_path):
    setup_repo(tmp_path)
    (tmp_path / "ddk.toml").write_text(valid_draft().replace("draft = true", "draft = false"))
    env = environment()
    env["assurance"] = "trusted-local"
    case = await CaseBootstrapper(tmp_path).initialize(
        "Fix heading", observed_environment=(env, None)
    )
    fixed = next(i for i in case["inputs"] if i["path"] == "criteria/bootstrap.json")
    base = tmp_path / ".ddk/verified-change/1/cases" / case["case_id"] / "inputs"
    raw = (base / fixed["path"]).read_bytes()
    binding = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == fixed["sha256"]
    assert binding["selected_path"] == "ddk.toml"
    assert binding["files"][".ddk/verify.toml"] is None
    assert (
        binding["files"]["ddk.toml"]
        == hashlib.sha256((tmp_path / "ddk.toml").read_bytes()).hexdigest()
    )


def test_discovery_and_approval_flags_are_shared_by_both_init_routes(tmp_path):
    runner = CliRunner()
    for command in (["init"], ["change", "init"]):
        result = runner.invoke(
            app, [*command, "--repo", str(tmp_path), "--discover", "--dry-run", "--json"]
        )
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["draft"] is True
    assert not (tmp_path / ".ddk").exists()


async def test_discovery_mcp_uses_the_same_draft_and_owner_grants(tmp_path, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    from ddk.server import mcp

    monkeypatch.delenv("DDK_MCP_CAPABILITIES", raising=False)
    reply = await mcp.call_tool(
        "ddk_init",
        {"request": "Fix login", "repository": str(tmp_path), "discover": True, "dry_run": True},
    )
    text = reply[0][0].text if isinstance(reply, tuple) else reply[0].text
    assert json.loads(text)["draft"] is True
    with pytest.raises(ToolError):
        await mcp.call_tool(
            "ddk_init",
            {
                "request": "Fix login",
                "repository": str(tmp_path),
                "discover": True,
                "dry_run": False,
                "approved": True,
            },
        )
    assert not (tmp_path / ".ddk").exists()


async def test_discovery_uses_playwright_native_report_without_an_untracked_output(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "playwright test"}}))
    result = await CaseBootstrapper(tmp_path).discover(dry_run=True)
    check = next(c for c in result["checks"] if c["kind"] == "test")
    assert check["report_adapter"] == "playwright-json"
    assert any("{report}" in arg for arg in check["command_argv"])


async def test_playwright_config_suggests_a_local_runner_without_evaluating_javascript(tmp_path):
    (tmp_path / "playwright.config.ts").write_text("throw new Error('must not execute');")
    result = await CaseBootstrapper(tmp_path).discover(dry_run=True)
    check = next(c for c in result["checks"] if c.get("report_adapter") == "playwright-json")
    assert "--no-install" in check["command_argv"]
    assert any("{report}" in arg for arg in check["command_argv"])


async def test_bootstrap_rejects_configuration_changes_during_observation(tmp_path, monkeypatch):
    from ddk.services import case_bootstrapper

    setup_repo(tmp_path)
    config = tmp_path / "ddk.toml"
    config.write_text(valid_draft().replace("draft = true", "draft = false"))

    async def changed(repository):
        config.write_text(config.read_text().replace('value = "After"', 'value = "Unreviewed"'))
        env = environment()
        env["assurance"] = "trusted-local"
        return env, None

    monkeypatch.setattr(case_bootstrapper, "observe_environment", changed)
    with pytest.raises(ValueError, match="bootstrap_configuration_changed"):
        await CaseBootstrapper(tmp_path).initialize("Fix heading")
    assert not (tmp_path / ".ddk/verified-change/1/cases").exists()


async def test_design_cannot_publish_unapproved_draft(tmp_path):
    setup_repo(tmp_path)
    design = tmp_path / "design"
    design.mkdir()
    (design / "manifest.json").write_text('{"requirements":[]}')
    (design / "verification.json").write_text(json.dumps(tomllib.loads(valid_draft())))
    result = await CaseBootstrapper(tmp_path).initialize(
        "Fix heading", from_design=design, dry_run=True
    )
    assert result["status"] == "blocked"
    assert result["actions"][0]["code"] == "draft_criteria_unapproved"


@pytest.mark.parametrize(
    "replacement",
    [
        ('action = "expect-text"', 'action = "unrecognized-action"'),
        ('selector = "h1"', 'selector = ""'),
        (
            'preview_argv = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]',
            'preview_argv = [""]',
        ),
    ],
)
def test_draft_approval_validates_real_check_contract_before_publication(tmp_path, replacement):
    folder = tmp_path / ".ddk"
    folder.mkdir()
    (folder / "verify.draft.toml").write_text(valid_draft().replace(*replacement))
    with pytest.raises(ValueError):
        CaseBootstrapper(tmp_path).approve_draft()
    assert not (folder / "verify.toml").exists()


async def test_mcp_discovery_command_requires_host_execution_grant(tmp_path, monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    from ddk.server import mcp
    from ddk.services import case_bootstrapper

    reached = []

    async def capture(*args, **kwargs):
        reached.append(True)
        return {}

    monkeypatch.setattr(case_bootstrapper.CaseBootstrapper, "discover", capture)
    monkeypatch.setenv("DDK_MCP_CAPABILITIES", "init,probe")
    monkeypatch.setenv("DDK_MCP_REPOSITORY", str(tmp_path))
    with pytest.raises(ToolError, match="trusted-local"):
        await mcp.call_tool(
            "ddk_init",
            {
                "request": "Fix heading",
                "repository": str(tmp_path),
                "discover": True,
                "preview": "python3 -m http.server {port}",
                "confirm_execution": True,
                "dry_run": False,
                "approved": True,
            },
        )
    assert not reached

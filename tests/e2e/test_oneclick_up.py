from __future__ import annotations

import importlib
import json
import subprocess

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.services.verified_budget import ProviderResult, ProviderUsage
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_repair import RepairReply
from tests.unit.test_case_bootstrapper import setup_repo

pytestmark = pytest.mark.playwright

CONFIG = """preview_argv = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
scope_paths = ["index.html"]
[[checks]]
check_id = "target"
role = "target"
timeout_ms = 5000
steps = [{action="expect-text", selector="h1", value="After", timeout_ms=200}]
[[checks]]
check_id = "preserve"
role = "preserve"
timeout_ms = 5000
steps = [{action="click", selector="a"}, {action="expect-text", selector="h1", value="Next"}]
"""


@pytest.mark.parametrize("needs_repair", [False, True])
def test_up_runs_real_git_bootstrap_browser_export_and_candidate_bound_apply(
    tmp_path, monkeypatch, needs_repair
):
    setup_repo(tmp_path)
    icon = '<link rel="icon" href="data:,">'
    baseline = icon + '<h1>Before</h1><a href="/next.html">Continue</a>'
    (tmp_path / "index.html").write_text(baseline)
    (tmp_path / "next.html").write_text(icon + "<h1>Next</h1>")
    (tmp_path / "ddk.toml").write_text(CONFIG)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "fixed checks"], check=True)
    candidate = (
        icon
        + '<h1>After</h1><a href="/next.html">'
        + ("Broken" if needs_repair else "Continue")
        + "</a>"
    )
    (tmp_path / "index.html").write_text(candidate)
    if needs_repair:
        # The preservation check includes the original link label.
        config = (
            (tmp_path / "ddk.toml")
            .read_text()
            .replace('selector="a"', 'selector={strategy="role",value="link",name="Continue"}')
        )
        (tmp_path / "ddk.toml").write_text(config)
        subprocess.run(["git", "-C", str(tmp_path), "add", "ddk.toml"], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-qm", "explicit link assertion"], check=True
        )
    calls = []

    async def provider(request):
        calls.append(request)
        payload = json.dumps(
            {
                "patches": [
                    {"path": "index.html", "hunks": [{"search": "Broken", "replace": "Continue"}]}
                ]
            }
        )
        return ProviderResult(
            RepairReply(payload, False, len(payload.encode())),
            ProviderUsage(1, 1, 0),
            "anthropic",
            "claude-sonnet-5-5",
        )

    oneclick = importlib.import_module("ddk.cli.oneclick")
    monkeypatch.setattr(oneclick, "select_provider", lambda *a: provider)
    args = [
        "up",
        "Change heading and preserve navigation",
        "--repo",
        str(tmp_path),
        "--trusted-local",
        "--apply",
        "--confirm-quiescence",
        "--confirm-local-storage",
        "--json",
    ]
    if needs_repair:
        args += ["--repair", "--confirm-provider"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, (result.output, result.exception)
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "ready" and receipt["application"]["state"] == "applied"
    assert (
        tmp_path / "index.html"
    ).read_text() == icon + '<h1>After</h1><a href="/next.html">Continue</a>'
    assert len(calls) == int(needs_repair)
    store = VerifiedChangeStore(tmp_path, create=False)
    assert store.run(receipt["run_id"])["decision"] == "ready"

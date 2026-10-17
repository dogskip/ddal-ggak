from __future__ import annotations

import subprocess
import sys
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_gate import gate_status
from tests.public_contract import public_payload
from tests.unit.adapters.test_verified_browser import environment
from tests.unit.test_case_bootstrapper import setup_repo
from tests.unit.test_case_discovery import valid_draft
from tests.unit.test_verified_change_engine import Evaluator


@pytest.fixture
async def gated(tmp_path):
    setup_repo(tmp_path)
    (tmp_path / ".ddk").mkdir()
    (tmp_path / ".ddk/verify.toml").write_text(
        valid_draft().replace("draft = true", "draft = false")
    )
    env = environment()
    env["assurance"] = "trusted-local"
    case = await CaseBootstrapper(tmp_path).initialize(
        "Heading changes", observed_environment=(env, None)
    )
    (tmp_path / "index.html").write_text("<h1>After</h1>")
    store = VerifiedChangeStore(tmp_path)
    run = await VerifiedChangeEngine(store, Evaluator()).verify(
        case["case_id"],
        baseline=None,
        candidate=None,
        git_base="HEAD",
        run_id=str(uuid4()),
        change_requirements={"index.html": ["REQ-001"]},
    )
    assert run["decision"] == "ready", run["actions"]
    return store, case, run


def test_gate_with_no_records_is_read_only_and_blocked(tmp_path):
    result = gate_status(tmp_path)
    assert result["gate_status"] == "blocked"
    assert not (tmp_path / ".ddk").exists()


async def test_gate_uses_canonical_records_even_without_or_with_forged_sqlite(gated):
    store, _, run = gated
    catalog = store.base_path / "index.sqlite3"
    catalog.unlink()
    result = gate_status(store.repository)
    assert result["gate_status"] == "passed" and result["run_id"] == run["run_id"]
    catalog.write_bytes(b"forged database")
    assert gate_status(store.repository)["gate_status"] == "passed"


@pytest.mark.parametrize("change", ["bytes", "added", "deleted", "mode", "configuration"])
async def test_gate_reopens_on_every_material_source_or_criteria_change(gated, change):
    store, _, run = gated
    root = store.repository
    if change == "bytes":
        (root / "index.html").write_text("<h1>After!</h1>")
    elif change == "added":
        (root / "new.txt").write_text("new")
    elif change == "deleted":
        (root / "index.html").unlink()
    elif change == "mode":
        (root / "index.html").chmod(0o755)
    else:
        (root / ".ddk/verify.toml").write_text("draft = true\\n")
    result = gate_status(root)
    assert result["gate_status"] == "reopened", result
    assert result["changed_paths"]
    assert store.run(run["run_id"]) == run


async def test_pending_execution_cannot_fall_back_to_an_older_ready(gated):
    store, case, run = gated
    prepared = VerifiedChangeEngine._prepared(
        case, str(uuid4()), "a" * 64, run["candidate_tree_sha256"], run["changes"]
    )
    prepared["started_at"] = "2099-01-01T00:00:00Z"
    store.claim_run(prepared)
    result = gate_status(store.repository)
    assert result["gate_status"] == "blocked"
    assert result["run_id"] == prepared["run_id"]


async def test_gate_cli_exit_and_mcp_schema(gated):
    from ddk.server import mcp

    store, _, _ = gated
    runner = CliRunner()
    result = runner.invoke(app, ["change", "gate", "--repo", str(store.repository), "--json"])
    assert result.exit_code == 0, result.output
    assert public_payload(result.stdout)["gate_status"] == "passed"
    (store.repository / "index.html").write_text("changed")
    assert (
        runner.invoke(app, ["change", "gate", "--repo", str(store.repository), "--json"]).exit_code
        == 5
    )
    tools = {t.name: t for t in await mcp.list_tools()}
    assert tools["ddk_gate_status"].inputSchema["additionalProperties"] is False


async def test_gate_cannot_pass_when_a_new_run_starts_during_tree_capture(gated, monkeypatch):
    from ddk.services import verified_gate

    store, case, run = gated
    original = verified_gate.capture_git_worktree
    created = False

    def changed(*args, **kwargs):
        nonlocal created
        if not created:
            created = True
            prepared = VerifiedChangeEngine._prepared(
                case, str(uuid4()), "b" * 64, run["candidate_tree_sha256"], run["changes"]
            )
            prepared["started_at"] = "2099-01-01T00:00:00Z"
            store.claim_run(prepared)
        return original(*args, **kwargs)

    monkeypatch.setattr(verified_gate, "capture_git_worktree", changed)
    assert gate_status(store.repository)["gate_status"] != "passed"


async def test_gate_rechecks_private_configuration_after_source_capture(gated, monkeypatch):
    from ddk.services import verified_gate

    store, _, _ = gated
    original = verified_gate.capture_git_worktree

    def changed(*args, **kwargs):
        (store.repository / ".ddk/verify.toml").write_text("draft = true\\n")
        return original(*args, **kwargs)

    monkeypatch.setattr(verified_gate, "capture_git_worktree", changed)
    assert gate_status(store.repository)["gate_status"] == "reopened"


async def test_pre_push_checks_actual_commit_tips_instead_of_only_working_files(gated):
    from ddk.services.verified_gate import pre_push_status

    store, _, _ = gated
    root = store.repository

    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()

    old = git("rev-parse", "HEAD")

    def update(sha):
        return f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n".encode()

    assert pre_push_status(root, update(old))["gate_status"] == "reopened"
    git("add", "index.html")
    git("commit", "-qm", "verified change")
    tip = git("rev-parse", "HEAD")
    assert pre_push_status(root, update(tip))["gate_status"] == "passed"
    assert pre_push_status(root, update(tip) + update(old))["gate_status"] != "passed"
    assert pre_push_status(root, b"malformed\n")["gate_status"] == "blocked"
    assert pre_push_status(root, b"x" * (2 * 1024**2 + 1))["gate_status"] == "blocked"


async def test_actual_pre_push_script_passes_git_stdin_to_commit_gate(gated):
    import os
    from pathlib import Path

    from ddk import installer

    store, _, _ = gated
    installer.install_hooks(store.repository)
    sha = (
        subprocess.check_output(["git", "-C", str(store.repository), "rev-parse", "HEAD"])
        .decode()
        .strip()
    )
    result = subprocess.run(
        ["/bin/sh", str(store.repository / ".git/hooks/pre-push")],
        input=f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n".encode(),
        cwd=store.repository,
        env={
            **os.environ,
            "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"],
        },
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 5, result.stdout + result.stderr
    assert public_payload(result.stdout)["gate_status"] == "reopened"


async def test_pre_push_rechecks_latest_execution_across_all_cases(gated, monkeypatch):
    import copy

    from ddk.services import verified_gate

    store, case, run = gated
    root = store.repository
    for args in (["add", "index.html"], ["commit", "-qm", "candidate"]):
        subprocess.run(["git", "-C", str(root), *args], check=True)
    sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"]).decode().strip()
    original = verified_gate.capture_git_source

    def start_another_case(*args, **kwargs):
        other = copy.deepcopy(case)
        other["case_id"] = str(uuid4())
        inputs = {
            i["path"]: (store.path_for("case", case["case_id"]) / "inputs" / i["path"]).read_bytes()
            for i in case["inputs"]
        }
        store.publish_case(other, inputs)
        prepared = VerifiedChangeEngine._prepared(
            other, str(uuid4()), "c" * 64, run["candidate_tree_sha256"], run["changes"]
        )
        prepared["started_at"] = "2099-01-01T00:00:00Z"
        store.claim_run(prepared)
        return original(*args, **kwargs)

    monkeypatch.setattr(verified_gate, "capture_git_source", start_another_case)
    result = verified_gate.pre_push_status(
        root, f"refs/heads/main {sha} refs/heads/main {'0' * 40}\n".encode()
    )
    assert result["gate_status"] == "blocked"


async def test_gate_handles_individually_bounded_records_exceeding_one_frame_in_total(gated):
    store, case, run = gated
    for _ in range(2):
        previous = VerifiedChangeEngine._prepared(
            case, str(uuid4()), "d" * 64, run["candidate_tree_sha256"], run["changes"]
        )
        previous["started_at"] = "2020-01-01T00:00:00Z"
        previous["actions"] = [
            {"code": "pending_action", "target": "run", "message": "x" * 2000, "retryable": False}
            for _ in range(600)
        ]
        store.claim_run(previous)
    assert gate_status(store.repository)["gate_status"] == "passed"

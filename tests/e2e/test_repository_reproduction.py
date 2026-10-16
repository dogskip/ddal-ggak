"""Fixed synthetic repositories, with real native tests and headless observations."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest
from typer.testing import CliRunner

import ddk
from ddk.adapters.verified_browser import BrowserSettings
from ddk.cli import app
from ddk.models.verified_change import canonical_json, record_digest
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.case_discovery import _toml
from ddk.services.source_snapshot import capture_git_worktree
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_host import observe_environment
from tests.e2e.test_verified_isolated import images as images
from tests.e2e.test_verified_isolated import isolated_settings as isolated_settings
from tests.e2e.test_verified_isolated import owned_containers

FIXTURES = Path(__file__).parents[1] / "fixtures/reproduction"
SPECS = {
    "python": {
        "path": "pricing.py",
        "preview": ["python3", "serve.py", "{port}"],
        "test": ["python3", "checks.py"],
        "adapter": "ddk-json",
        "target": "18.00",
        "preserve": "20.00",
        "old": "1.0 if discounted",
        "new": "0.9 if discounted",
        "missed": "0.8 if discounted",
        "regression_old": "else 1.0",
        "regression_new": "else 1.1",
        "tests": 2,
    },
    "javascript": {
        "path": "label.cjs",
        "preview": ["node", "serve.cjs", "{port}"],
        "test": [
            "node",
            "--test",
            "--test-reporter=junit",
            "--test-reporter-destination={report}",
            "label.test.cjs",
        ],
        "adapter": "junit-xml",
        "target": "hello-world",
        "preserve": "(empty)",
        "old": "value.trim()",
        "new": "value.trim().toLowerCase().replaceAll(' ', '-')",
        "missed": "value.trim().toLowerCase().replaceAll(' ', '_')",
        "regression_old": "'(empty)'",
        "regression_new": "'missing'",
        "tests": 2,
    },
    "browser": {
        "path": "counter.js",
        "preview": ["node", "serve.cjs", "{port}"],
        "test": [
            "node",
            "--test",
            "--test-reporter=junit",
            "--test-reporter-destination={report}",
            "counter.test.cjs",
        ],
        "adapter": "junit-xml",
        "target": "1",
        "preserve": "0",
        "old": "value + 2",
        "new": "value + 1",
        "missed": "value + 3",
        "regression_old": "return 0",
        "regression_new": "return 1",
        "tests": 1,
    },
}


@pytest.fixture(scope="module")
async def host_settings(tmp_path_factory):
    repository = tmp_path_factory.mktemp("reproduction-environment")
    (repository / "package-lock.json").write_bytes(b"{}")
    env, binary = await observe_environment(repository)
    return BrowserSettings(env, record_digest(env), "2026-10-16T00:00:00+00:00", binary)


def configuration(name, settings):
    spec = SPECS[name]
    target = [{"action": "click", "selector": "#add"}] if name == "browser" else []
    preserve = (
        [{"action": "click", "selector": "#add"}, {"action": "click", "selector": "#reset"}]
        if name == "browser"
        else [{"action": "click", "selector": "a"}]
    )
    checks = [
        {
            "check_id": "native-tests",
            "role": "preserve",
            "kind": "test",
            "command_argv": spec["test"],
            "report_adapter": spec["adapter"],
        }
    ]
    for role, steps in (("target", target), ("preserve", preserve)):
        checks.append(
            {
                "check_id": role,
                "role": role,
                "viewport": {"width": 320, "height": 300},
                "steps": [
                    *steps,
                    {
                        "action": "expect-text",
                        "selector": "#value",
                        "value": spec[role],
                        "timeout_ms": 300,
                    },
                    {"action": "expect-no-console-error"},
                ],
            }
        )
    return {
        "scope_paths": [spec["path"]],
        "preview_argv": spec["preview"],
        "frozen_time": settings.frozen_time,
        "checks": checks,
    }


def reproduce(tmp_path, settings, name, variant, runtime):
    started = time.monotonic()
    package = Path(ddk.__file__).resolve().parent
    if os.environ.get("DDK_REPRO_EXPECT_INSTALLED") == "1":
        assert package.is_relative_to(Path(sys.prefix).resolve())
        assert not package.is_relative_to(Path(__file__).resolve().parents[2] / "src")
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / name, project, ignore=shutil.ignore_patterns("__pycache__"))
    (project / "package-lock.json").write_bytes(b"{}")
    (project / ".gitignore").write_text("__pycache__/\n.ddk/\n")
    (project / "ddk.toml").write_bytes(_toml(configuration(name, settings)))
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    git = ["git", "-C", str(project), "-c", "core.hooksPath=/dev/null"]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run(
        [
            *git,
            "-c",
            "user.name=Reproduction",
            "-c",
            "user.email=reproduction@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixed acceptance",
        ],
        check=True,
    )
    spec = SPECS[name]
    path = project / spec["path"]
    old = path.read_text()
    candidate = old.replace(
        spec["old"], spec["missed"] if variant == "target-missed" else spec["new"]
    )
    if variant == "regression":
        candidate = candidate.replace(spec["regression_old"], spec["regression_new"])
    assert candidate != old
    path.write_text(candidate)
    before = capture_git_worktree(project).tree_sha256
    containers = owned_containers() if runtime == "isolated" else None
    case = asyncio.run(
        CaseBootstrapper(project).initialize(
            f"Reproduce {name}: change target and preserve existing behavior.",
            observed_environment=(settings.environment, settings.executable_path),
        )
    )
    assert case.get("case_id"), case
    run_id = str(uuid4())
    requirements = tmp_path / "requirements.json"
    requirements.write_text(json.dumps({spec["path"]: ["REQ-001"]}))
    argv = [
        "change",
        "verify",
        "--repo",
        str(project),
        "--case-id",
        case["case_id"],
        "--git-base",
        "HEAD",
        "--run-id",
        run_id,
        "--change-requirements",
        str(requirements),
        "--json",
    ]
    if runtime == "host":
        argv.append("--trusted-local")
    response = CliRunner().invoke(app, argv)
    record = json.loads(response.stdout)
    destination = os.environ.get("DDK_REPRO_EVIDENCE_DIR")
    if destination:
        saved = Path(destination) / "runs" / f"{runtime}-{name}-{variant}"
        saved.mkdir(parents=True)
        (saved / "cli.json").write_text(response.stdout)
        shutil.copytree(project / ".ddk/verified-change/1", saved / "canonical")
    wanted = "ready" if variant == "ready" else "blocked"
    assert record.get("decision") == wanted, record
    assert response.exit_code == (0 if wanted == "ready" else 1), response.stdout
    assert record["assurance"] == ("trusted-local" if runtime == "host" else "isolated")
    assert record["model_calls"] == []
    assert record["integrity"]["cleanup_complete"]
    assert record["workspace_leases"] and all(
        row["state"] == "released" for row in record["workspace_leases"]
    )
    results = {(r["phase"], r["check_id"]): r for r in record["results"]}
    assert results["baseline", "target"]["status"] == "failed"
    assert results["baseline", "preserve"]["status"] == "passed"
    assert results["candidate", "target"]["status"] == (
        "failed" if variant == "target-missed" else "passed"
    )
    assert results["candidate", "preserve"]["status"] == (
        "failed" if variant == "regression" else "passed"
    )
    for phase in ("baseline", "candidate"):
        native = results[phase, "native-tests"]
        assert native["executed_count"] == spec["tests"], native
        assert native["failed_count"] == int(phase == "candidate" and variant == "regression"), (
            native
        )
        assert native["skipped_count"] == 0
    store = VerifiedChangeStore(project, create=False)
    for artifact in record["artifacts"]:
        data = (store.path_for("run", run_id) / artifact["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
    assert any(a["kind"] == "screenshot" for a in record["artifacts"])
    replay_response = CliRunner().invoke(
        app,
        [
            "change",
            "replay",
            "--repo",
            str(project),
            "--run-id",
            run_id,
            "--json",
        ],
    )
    replay = json.loads(replay_response.stdout)
    assert replay_response.exit_code == 0 and replay["evidence_integrity"], replay
    assert replay["replay_decision"] == wanted and not replay["execution_repeated"]
    gate_response = CliRunner().invoke(app, ["change", "gate", "--repo", str(project), "--json"])
    gate = json.loads(gate_response.stdout)
    assert gate["gate_status"] == ("passed" if wanted == "ready" else "blocked"), gate
    assert capture_git_worktree(project).tree_sha256 == before
    if runtime == "isolated":
        assert owned_containers() == containers
    row = {
        "repository": name,
        "variant": variant,
        "runtime": runtime,
        "decision": record["decision"],
        "assurance": record["assurance"],
        "run_id": run_id,
        "case_sha256": record_digest(case),
        "package_directory": str(package),
        "isolated_evaluator_sha256": hashlib.sha256(
            (package / "adapters/isolated_evaluator.py").read_bytes()
        ).hexdigest(),
        "run_sha256": record_digest(record),
        "source_sha256": before,
        "source_preserved": True,
        "environment": settings.environment,
        "cleanup_complete": True,
        "evidence_integrity": replay["evidence_integrity"],
        "replay_decision": replay["replay_decision"],
        "gate_status": gate["gate_status"],
        "model_calls": len(record["model_calls"]),
        "actual_cost_micro_usd": 0,
        "duration_s": round(time.monotonic() - started, 3),
        "results": [
            {
                k: r[k]
                for k in (
                    "phase",
                    "check_id",
                    "status",
                    "reason_code",
                    "executed_count",
                    "failed_count",
                    "skipped_count",
                )
            }
            for r in record["results"]
        ],
    }
    if destination:
        receipts = Path(destination) / "receipts"
        receipts.mkdir(exist_ok=True)
        (receipts / f"{runtime}-{name}-{variant}.json").write_bytes(canonical_json(row))


@pytest.mark.playwright
@pytest.mark.parametrize("name", SPECS)
@pytest.mark.parametrize("variant", ["ready", "target-missed", "regression"])
def test_host_repositories(tmp_path, host_settings, name, variant):
    reproduce(tmp_path, host_settings, name, variant, "host")


@pytest.mark.docker
@pytest.mark.parametrize("name", SPECS)
@pytest.mark.parametrize("variant", ["ready", "target-missed", "regression"])
def test_isolated_repositories(tmp_path, isolated_settings, name, variant):
    reproduce(tmp_path, isolated_settings, name, variant, "isolated")

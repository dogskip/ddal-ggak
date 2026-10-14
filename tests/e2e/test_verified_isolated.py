"""Opt-in real Docker checks; never install, pull or relax a boundary in tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from dataclasses import replace

import pytest

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.isolated_evaluator import _ENTRY, _NODE_ENV, write_worker_bundle
from ddk.adapters.verified_browser import BrowserSettings
from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.adapters.verified_isolation import IsolationRequest, LocalDockerIsolation
from ddk.models.verified_change import canonical_json, decode_json, record_digest
from ddk.services.source_snapshot import capture_source
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore
from tests.e2e.test_verified_evaluator import scenario
from tests.unit.adapters.test_verified_browser import FIXTURE, environment
from tests.unit.test_verified_change_engine import RUN_ID, fixed_file

pytestmark = pytest.mark.docker


@pytest.fixture(scope="module")
def images():
    if os.environ.get("DDK_DOCKER_E2E") != "1":
        pytest.skip("Set DDK_DOCKER_E2E=1 and immutable local image IDs")
    return os.environ["DDK_APP_IMAGE"], os.environ["DDK_CHECKER_IMAGE"]


@pytest.fixture(scope="module")
async def isolated_settings(tmp_path_factory, images):
    from ddk.adapters.verified_isolation import POLICY_SHA256

    request = isolation_request(tmp_path_factory.mktemp("isolated-environment"), images)
    write_worker_bundle(request.criteria_dir)
    isolation = LocalDockerIsolation()
    availability = await isolation.preflight()

    async def operation(session):
        checker = await session.checker(
            _ENTRY,
            timeout_s=15,
            stdin=canonical_json({"mode": "probe", "browser_executable": None}),
        )
        assert checker.success, checker.stderr
        app = await session.app(("node", "-e", _NODE_ENV, "npm"), timeout_s=5)
        assert app.success, app.stderr
        return BuildResult(
            True,
            canonical_json(
                {**decode_json(checker.stdout.encode()), **decode_json(app.stdout.encode())}
            ).decode(),
            "",
            0,
        )

    result = await isolation.execute(request, b"", operation=operation)
    assert result.completed, result
    env = environment()
    env.update(
        decode_json(result.stdout.encode()),
        assurance="isolated",
        endpoint_kind="local",
        runtime_name="docker",
        runtime_version=availability.runtime_version,
        app_image_sha256=images[0].removeprefix("sha256:"),
        checker_image_sha256=images[1].removeprefix("sha256:"),
        package_manager="npm",
        lockfile_sha256=hashlib.sha256(b"{}").hexdigest(),
        policy_sha256=POLICY_SHA256,
        locale="en-US",
        timezone="UTC",
        fixture_sha256=FIXTURE,
    )
    return BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00")


def isolated_scenario(tmp_path, settings, candidate):
    case, old_store, _ = scenario(tmp_path, settings, candidate)
    payloads = {
        item["path"]: (
            old_store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    for name in ("baseline", "candidate"):
        (tmp_path / name / "package-lock.json").write_bytes(b"{}")
        (tmp_path / name / "package-lock.json").chmod(0o644)
    snapshots = {name: capture_source(tmp_path / name) for name in ("baseline", "candidate")}
    lock = fixed_file("package-lock.json", b"{}")
    case["inputs"].append({**lock.manifest_entry(), "role": "source"})
    payloads[lock.path] = lock.content
    case.update(
        assurance_required="isolated", baseline_tree_sha256=snapshots["baseline"].tree_sha256
    )
    case["limits"].update(run_timeout_ms=120000, step_timeout_ms=20000)
    store = VerifiedChangeStore(tmp_path / "isolated-records")
    store.publish_case(case, payloads)
    return case, store, snapshots


@pytest.mark.parametrize("candidate", ["ready", "regression", "spoofed", "external"])
async def test_real_default_engine_observes_versions_and_blocks_regressions(
    tmp_path, isolated_settings, candidate
):
    before = owned_containers()
    case, store, snapshots = isolated_scenario(tmp_path, isolated_settings, candidate)
    if candidate == "external":
        path = tmp_path / "candidate/index.html"
        path.write_bytes(
            path.read_bytes() + b"<script>fetch('https://example.invalid/blocked')</script>"
        )
        snapshots["candidate"] = capture_source(tmp_path / "candidate")
    record = await VerifiedChangeEngine(store, VerifiedEvaluator()).verify(
        case["case_id"],
        baseline=tmp_path / "baseline",
        candidate=tmp_path / "candidate",
        run_id=RUN_ID,
        change_requirements={"index.html": ["target"]},
    )
    assert record["decision"] == ("ready" if candidate == "ready" else "blocked"), record
    assert record["assurance"] == "isolated"
    assert record["integrity"]["cleanup_complete"] and record["model_calls"] == []
    observed = {row["check_id"]: row for row in record["results"] if row["phase"] == "candidate"}
    assert observed["tests"]["status"] == "passed"
    if candidate == "regression":
        assert observed["preserve"]["status"] == "failed"
    elif candidate == "spoofed":
        assert observed["target"]["status"] == "failed"
    elif candidate == "ready":
        assert all(row["status"] == "passed" for row in observed.values())
    else:
        observations = [
            decode_json((store.path_for("run", RUN_ID) / row["path"]).read_bytes())
            for row in record["artifacts"]
            if row["kind"] == "data" and "/browser-" in row["path"]
        ]
        assert any(
            error["code"] == "external_request_blocked"
            for item in observations
            for error in item["errors"]
        )
    assert all(
        capture_source(tmp_path / name).tree_sha256 == snapshot.tree_sha256
        for name, snapshot in snapshots.items()
    )
    assert owned_containers() == before
    destination = os.environ.get("DDK_ISOLATED_EVIDENCE_DIR")
    if destination:
        import shutil
        from pathlib import Path

        output = Path(destination).resolve() / candidate
        output.mkdir(parents=True, exist_ok=True)
        run = store.path_for("run", RUN_ID)
        for row in record["artifacts"]:
            path = output / row["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run / row["path"], path)
        (output / "run.json").write_bytes(canonical_json(record))


def test_real_default_cli_and_mcp_share_isolated_result(tmp_path, isolated_settings, monkeypatch):
    from typer.testing import CliRunner

    from ddk.cli import app
    from tests.integration.test_verified_mcp_stdio import connected

    before = owned_containers()
    for name in ("ANTHROPIC_API_KEY", "DDK_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    case, store, _ = isolated_scenario(tmp_path, isolated_settings, "ready")
    requirements = tmp_path / "requirements.json"
    requirements.write_text('{"index.html":["target"]}')
    answer = CliRunner().invoke(
        app,
        [
            "change",
            "verify",
            "--repo",
            str(store.repository),
            "--case-id",
            case["case_id"],
            "--baseline",
            str(tmp_path / "baseline"),
            "--candidate",
            str(tmp_path / "candidate"),
            "--run-id",
            RUN_ID,
            "--change-requirements",
            str(requirements),
            "--json",
        ],
    )
    assert answer.exit_code == 0, answer.output
    record = json.loads(answer.stdout)
    assert record["decision"] == "ready" and record["assurance"] == "isolated"
    assert record["integrity"]["cleanup_complete"] and record["model_calls"] == []

    async def check_mcp():
        async with connected(tmp_path, monkeypatch) as (session, _):
            result = await session.call_tool(
                "ddk_status", {"run_id": RUN_ID, "repository": str(store.repository)}
            )
            assert not result.isError
            assert json.loads(result.content[0].text) == record
            result = await session.call_tool(
                "ddk_verify",
                {
                    "case_id": case["case_id"],
                    "run_id": RUN_ID,
                    "repository": str(store.repository),
                    "baseline": str(tmp_path / "baseline"),
                    "candidate": str(tmp_path / "candidate"),
                    "change_requirements": {"index.html": ["target"]},
                },
            )
            assert not result.isError
            assert json.loads(result.content[0].text) == record

    asyncio.run(check_mcp())
    assert owned_containers() == before


@pytest.mark.parametrize("color", ["red", "blue"])
async def test_real_isolated_rgb_comparison_uses_frozen_reference(
    tmp_path, isolated_settings, color
):
    import time
    from dataclasses import replace

    from ddk.services.source_snapshot import manifest_digest
    from tests.e2e.test_verified_evaluator import SERVER, flow
    from tests.unit.adapters.test_verified_browser import png, step
    from tests.unit.adapters.test_verified_evaluator import request_for

    request, original, _ = request_for(
        tmp_path, kind="visual", argv=[], env_changes=isolated_settings.environment
    )
    (original / "serve.cjs").write_bytes(SERVER)
    (original / "package-lock.json").write_bytes(b"{}")
    (original / "index.html").write_text(
        "<!doctype html><link rel='icon' href='data:,'>"
        + f"<style>html,body{{margin:0;width:100%;height:100%;background:{color}}}</style>"
    )
    snapshot = capture_source(original)
    definition = fixed_file(
        "criteria/check.json",
        flow(
            "check-command",
            [
                step(
                    "snapshot",
                    reference_path="references/approved.png",
                    rgb_tolerance=0,
                    max_mismatch_ppm=0,
                )
            ],
        ),
    )
    reference = fixed_file("references/approved.png", png((255, 0, 0), (320, 200)))
    plan = decode_json(request.frozen_inputs[0].content)
    plan.update(
        preview_argv=["node", "serve.cjs", "{port}"],
        visual_references=[
            {
                "path": reference.path,
                "viewport": {"width": 320, "height": 200},
                "environment_sha256": record_digest(isolated_settings.environment),
                "mask_sha256": None,
            }
        ],
    )
    frozen = (
        fixed_file("criteria/execution.json", canonical_json(plan)),
        definition,
        fixed_file("environment/environment.json", canonical_json(isolated_settings.environment)),
        reference,
    )
    check = dict(
        request.checks[0],
        definition_sha256=definition.sha256,
        viewport={"width": 320, "height": 200},
        timeout_ms=15000,
    )
    request = replace(
        request,
        checks=(check,),
        snapshot=snapshot,
        input_tree_sha256=snapshot.tree_sha256,
        frozen_inputs=frozen,
        evaluator_sha256=manifest_digest(frozen[:2]),
        environment_sha256=manifest_digest(frozen[2:3]),
        deadline_ns=time.monotonic_ns() + 30_000_000_000,
    )
    before = owned_containers()
    outcome = await VerifiedEvaluator().evaluate(request)
    assert outcome.results[0]["status"] == ("passed" if color == "red" else "failed"), outcome
    assert outcome.assurance == "isolated" and outcome.cleanup_complete
    assert any(row.kind == "screenshot" for row in outcome.artifacts)
    assert capture_source(original).tree_sha256 == snapshot.tree_sha256
    assert owned_containers() == before
    persist_outcome("visual-" + color, outcome)


@pytest.mark.parametrize("guard", ["source", "output"])
async def test_real_isolated_command_guard_preserves_original(tmp_path, isolated_settings, guard):
    import time
    from dataclasses import replace

    from tests.unit.adapters.test_verified_evaluator import request_for

    command = (
        "require('fs').writeFileSync('index.html','changed')"
        if guard == "source"
        else "console.log('한'.repeat(20))"
    )
    request, original, _ = request_for(
        tmp_path, argv=["node", "-e", command], env_changes=isolated_settings.environment
    )
    (original / "package-lock.json").write_bytes(b"{}")
    snapshot = capture_source(original)
    request = replace(
        request,
        snapshot=snapshot,
        input_tree_sha256=snapshot.tree_sha256,
        checks=(dict(request.checks[0], timeout_ms=15000),),
        deadline_ns=time.monotonic_ns() + 30_000_000_000,
        limits={**request.limits, "max_output_bytes": 32},
    )
    before = owned_containers()
    outcome = await VerifiedEvaluator().evaluate(request)
    assert outcome.results[0]["reason_code"] == (
        "source_changed" if guard == "source" else "output_limit"
    ), outcome
    assert outcome.cleanup_complete
    assert outcome.input_tree_sha256 == (None if guard == "source" else snapshot.tree_sha256)
    if guard == "output":
        assert outcome.output_bytes == 61
    assert capture_source(original).tree_sha256 == snapshot.tree_sha256
    assert owned_containers() == before
    persist_outcome("guard-" + guard, outcome)


def persist_outcome(name, outcome):
    from pathlib import Path

    destination = os.environ.get("DDK_ISOLATED_EVIDENCE_DIR")
    if not destination:
        return
    output = Path(destination).resolve() / name
    output.mkdir(parents=True, exist_ok=True)
    for row in outcome.artifacts:
        path = output / row.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(row.content)
    (output / "outcome.json").write_bytes(
        canonical_json(
            {
                "results": list(outcome.results),
                "assurance": outcome.assurance,
                "cleanup_complete": outcome.cleanup_complete,
                "output_bytes": outcome.output_bytes,
                "input_tree_sha256": outcome.input_tree_sha256,
                "artifacts": [row.record() for row in outcome.artifacts],
            }
        )
    )


def isolation_request(tmp_path, images):
    root = tmp_path / "owned"
    root.mkdir()
    for name in ("app", "criteria", "results"):
        (root / name).mkdir()
    (root / "criteria" / "private.txt").write_text("approved criteria")
    return IsolationRequest(
        root,
        root / "app",
        root / "criteria",
        root / "results",
        *images,
        ("node", "-e", "setInterval(()=>{},1000)"),
        ("python3", "-I", "-c", "print('verified')"),
        timeout_s=30,
    )


def owned_containers():
    output = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=io.ddk.isolation.owner"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return set(output.stdout.split())


async def test_real_policy_and_separate_mounts_with_headless_browser(tmp_path, images):
    before = owned_containers()
    request = replace(
        isolation_request(tmp_path, images),
        app_command=("node", "-e", "console.log('startup-captured');setInterval(()=>{},1000)"),
    )

    async def operation(session):
        app = await session.app(
            (
                "node",
                "-e",
                "const f=require('fs'); console.log(JSON.stringify("
                "['/criteria','/results','/var/run/docker.sock'].map(p=>f.existsSync(p))))",
            ),
            timeout_s=3,
        )
        checker = await session.checker(
            (
                "python3",
                "-I",
                "-c",
                "import os,json; print(json.dumps([os.path.exists('/workspace'),"
                "os.path.exists('/criteria/private.txt')]))",
            ),
            timeout_s=3,
        )
        assert json.loads(app.stdout) == [False, False, False]
        assert json.loads(checker.stdout) == [False, True]
        return BuildResult(True, "verified", "", 0)

    result = await LocalDockerIsolation().execute(request, b"", operation=operation)
    assert result.completed, result
    assert result.policy_verified and result.cleanup_complete
    assert result.app_stdout == "startup-captured\n" and result.app_output_complete
    assert result.evidence["browser"] == {
        "started": True,
        "headless": True,
        "chromium_sandbox": True,
    }
    assert owned_containers() == before


async def test_real_cancel_repeatedly_removes_descendants_and_owned_tasks(tmp_path, images):
    before = owned_containers()
    for index in range(2):
        folder = tmp_path / str(index)
        folder.mkdir()
        request = isolation_request(folder, images)
        started = asyncio.Event()

        async def operation(session, started=started):
            started.set()
            await session.app(
                (
                    "node",
                    "-e",
                    "require('child_process').spawn('node',['-e','setInterval(()=>{},1000)'],"
                    "{detached:true,stdio:'ignore'}).unref();setInterval(()=>{},1000)",
                ),
                timeout_s=15,
            )
            return BuildResult(True, "", "", 0)

        task = asyncio.create_task(
            LocalDockerIsolation().execute(request, b"", operation=operation)
        )
        await asyncio.wait_for(started.wait(), 25)
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError) as caught:
            await task
        assert any('"cleanup_complete": true' in note for note in caught.value.__notes__)
        assert owned_containers() == before

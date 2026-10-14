"""Execution requires frozen plans and an explicit local grant."""

from __future__ import annotations

import asyncio
import platform
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.adapters.verified_isolation import IsolationAvailability, LocalDockerIsolation
from ddk.models.verified_change import canonical_json, decode_json, record_digest
from ddk.services.source_snapshot import SourceSnapshot, capture_source, manifest_digest
from ddk.services.verified_change_engine import EvaluationRequest
from tests.unit.adapters.test_verified_browser import environment, png
from tests.unit.test_verified_change_engine import fixed_file


def request_for(tmp_path, *, kind="command", argv=None, plan_changes=None, env_changes=None):
    original = tmp_path / "original"
    original.mkdir()
    (original / "index.html").write_text("<h1>Original</h1>")
    snapshot = capture_source(original)
    env = environment()
    env.update(
        os_name=platform.system(),
        os_version=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        assurance="trusted-local",
    )
    env.update(env_changes or {})
    definition = fixed_file("criteria/check.json", b"{}")
    plan = {
        "format": "verified-evaluator/1",
        "environment_path": "environment/environment.json",
        "criteria_paths": ["criteria/execution.json", definition.path],
        "environment_paths": ["environment/environment.json"],
        "preview_argv": [],
        "frozen_time": "2026-10-14T00:00:00+00:00",
        "browser_executable": None,
        "visual_references": [],
    }
    plan.update(plan_changes or {})
    frozen = (
        fixed_file("criteria/execution.json", canonical_json(plan)),
        definition,
        fixed_file("environment/environment.json", canonical_json(env)),
    )
    check = {
        "check_id": "check-command",
        "role": "preserve",
        "required": True,
        "kind": kind,
        "definition_path": definition.path,
        "definition_sha256": definition.sha256,
        "command_argv": ["node", "-e", "console.log('ran')"] if argv is None else argv,
        "viewport": None,
        "timeout_ms": 1000,
    }
    request = EvaluationRequest(
        "00000000-0000-4000-8000-000000000001",
        (check,),
        "candidate",
        snapshot,
        frozen,
        manifest_digest(frozen[2:]),
        manifest_digest(frozen[:2]),
        snapshot.tree_sha256,
        time.monotonic_ns() + 10_000_000_000,
        lambda: False,
        {
            "max_file_bytes": 2 * 1024**2,
            "max_artifact_bytes": 200 * 1024**2,
            "max_output_bytes": 10 * 1024**2,
            "cleanup_timeout_ms": 10_000,
            "step_timeout_ms": 300_000,
        },
    )
    return request, original, env


@pytest.mark.parametrize("available", [False, True])
async def test_default_never_executes_on_host_even_if_case_requests_local(
    tmp_path, monkeypatch, available
):
    request, original, _ = request_for(tmp_path)
    isolation = AsyncMock()
    isolation.preflight.return_value = IsolationAvailability(available, "local_socket_unavailable")
    runner = AsyncMock()
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: runner)
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.assurance is None
    assert outcome.cleanup_complete
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[0]["reason_code"] == "isolation_unavailable"
    runner.run.assert_not_called()
    isolation.execute.assert_not_called()
    assert capture_source(original).tree_sha256 == request.snapshot.tree_sha256


async def test_local_command_uses_verified_private_copy_and_retains_project_origin(tmp_path):
    argv = [
        "node",
        "-e",
        "console.log(process.cwd())",
    ]
    request, original, _ = request_for(tmp_path, argv=argv)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.assurance == "trusted-local"
    assert outcome.cleanup_complete
    assert outcome.input_tree_sha256 == request.input_tree_sha256
    assert outcome.environment_sha256 == request.environment_sha256
    assert outcome.evaluator_sha256 == request.evaluator_sha256
    assert outcome.results[0]["status"] == "passed"
    assert outcome.results[0]["evidence_origin"] == "project-report"
    assert capture_source(original).tree_sha256 == request.snapshot.tree_sha256
    assert len(outcome.artifacts) == 1
    assert str(original).encode() not in outcome.artifacts[0].content
    assert not Path(outcome.artifacts[0].content.decode().splitlines()[0]).exists()


@pytest.mark.parametrize(
    ("report", "status", "reason"),
    [
        ('{"executed_count":2,"failed_count":0,"skipped_count":0}', "passed", None),
        (
            '{"executed_count":0,"failed_count":0,"skipped_count":0}',
            "unavailable",
            "test_report_incomplete",
        ),
        (
            '{"executed_count":2,"failed_count":0,"skipped_count":1}',
            "unavailable",
            "test_report_incomplete",
        ),
        ('{"executed_count":2,"failed_count":1,"skipped_count":0}', "failed", "test_failed"),
        (
            '{"executed_count":true,"failed_count":0,"skipped_count":0}',
            "unavailable",
            "test_report_invalid",
        ),
        (
            '{"executed_count":2,"failed_count":0,"skipped_count":0,"status":"passed"}',
            "unavailable",
            "test_report_invalid",
        ),
        (
            '{"executed_count":2,"executed_count":5,"failed_count":0,"skipped_count":0}',
            "unavailable",
            "test_report_invalid",
        ),
        (
            '{"executed_count":null,"failed_count":0,"skipped_count":0}',
            "unavailable",
            "test_report_invalid",
        ),
        ("2 passed", "unavailable", "test_report_invalid"),
    ],
)
async def test_test_report_is_strict_and_cannot_supply_trusted_observation(
    tmp_path, report, status, reason
):
    request, _, _ = request_for(
        tmp_path, kind="test", argv=["node", "-e", f"console.log({report!r})"]
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    result = outcome.results[0]
    assert result["status"] == status
    assert result["reason_code"] == reason
    assert result["evidence_origin"] == "project-report"
    assert outcome.cleanup_complete


@pytest.mark.parametrize(
    "fault",
    [
        "unknown_key",
        "missing_definition",
        "overlap",
        "traversal",
        "embedded_port",
        "no_zone",
        "criteria_hash",
        "environment_hash",
        "definition_hash",
        "snapshot_bytes",
        "snapshot_tree",
        "mode",
        "os",
        "assurance",
    ],
)
async def test_invalid_inputs_do_not_execute(tmp_path, monkeypatch, fault):
    plan_changes = {
        "unknown_key": {"trusted_local": True},
        "missing_definition": {"criteria_paths": ["criteria/execution.json"]},
        "overlap": {"environment_paths": ["environment/environment.json", "criteria/check.json"]},
        "traversal": {"environment_path": "../environment.json"},
        "embedded_port": {"preview_argv": ["node", "serve.js", "--port={port}"]},
        "no_zone": {"frozen_time": "2026-10-14T00:00:00"},
    }.get(fault)
    env_changes = (
        {"os_name": "other"}
        if fault == "os"
        else {"assurance": "isolated"}
        if fault == "assurance"
        else None
    )
    request, _, _ = request_for(tmp_path, plan_changes=plan_changes, env_changes=env_changes)
    if fault in {"criteria_hash", "environment_hash"}:
        key = "evaluator_sha256" if fault == "criteria_hash" else "environment_sha256"
        request = replace(request, **{key: "0" * 64})
    elif fault == "definition_hash":
        request = replace(request, checks=({**request.checks[0], "definition_sha256": "0" * 64},))
    elif fault in {"snapshot_bytes", "snapshot_tree", "mode"}:
        files = list(request.snapshot.files)
        if fault == "snapshot_bytes":
            files[0] = replace(files[0], content=b"forged")
        elif fault == "mode":
            files[0] = replace(files[0], mode=0o7777)
        snapshot = SourceSnapshot(
            tuple(files), "0" * 64 if fault == "snapshot_tree" else request.snapshot.tree_sha256
        )
        request = replace(request, snapshot=snapshot)
    runner = AsyncMock()
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: runner)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    runner.run.assert_not_called()


async def test_command_failure_and_deadline_are_not_success(tmp_path):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "process.exit(7)"])
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "failed"
    assert outcome.results[0]["exit_code"] == 7
    request = replace(
        request,
        checks=(
            {
                **request.checks[0],
                "command_argv": ["node", "-e", "setInterval(()=>{},1000)"],
                "timeout_ms": 50,
            },
        ),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[0]["reason_code"] == "timeout"
    assert outcome.cleanup_complete


async def test_preexisting_cancellation_starts_no_process(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path)
    request = replace(request, cancelled=lambda: True)
    runner = AsyncMock()
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: runner)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["reason_code"] == "cancelled"
    runner.run.assert_not_called()


async def test_task_cancellation_cleans_owned_command_and_copy(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "setInterval(()=>{},1000)"])
    from ddk.adapters.subprocess_build_runner import start_owned_process

    started = asyncio.Event()
    processes = []

    async def observe(*args, **kwargs):
        answer = await start_owned_process(*args, **kwargs)
        processes.append((answer[0], args[1]))
        started.set()
        return answer

    monkeypatch.setattr("ddk.adapters.subprocess_build_runner.start_owned_process", observe)
    task = asyncio.create_task(VerifiedEvaluator(trusted_local_approved=True).evaluate(request))
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processes[0][0].returncode is not None
    assert not processes[0][1].exists()


async def test_absent_local_socket_rejects_execution_without_docker_call(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path)
    runner = AsyncMock()
    isolation = LocalDockerIsolation(
        runner=runner,
        environ={"DOCKER_HOST": "unix://" + str(tmp_path / "absent.sock")},
        config_dir=tmp_path / "docker-config",
    )
    outcome = await VerifiedEvaluator(isolation=isolation).evaluate(request)
    assert outcome.results[0]["reason_code"] == "isolation_unavailable"
    assert outcome.artifacts[0].content == b"local_socket_unavailable"
    runner.run.assert_not_called()


@pytest.mark.parametrize("fault", [None, "mask", "environment", "viewport", "size", "missing"])
async def test_visual_reference_requires_frozen_approval(tmp_path, fault):
    request, _, env = request_for(tmp_path)
    image = fixed_file("references/approved.png", png((255, 0, 0), (320, 200)))
    plan = decode_json(request.frozen_inputs[0].content)
    reference = {
        "path": image.path,
        "viewport": {"width": 320, "height": 200},
        "environment_sha256": record_digest(env),
        "mask_sha256": None,
    }
    if fault == "mask":
        reference["mask_sha256"] = "a" * 64
    elif fault == "environment":
        reference["environment_sha256"] = request.environment_sha256
    elif fault == "viewport":
        reference["viewport"] = {"width": True, "height": 200}
    elif fault == "size":
        reference["viewport"] = {"width": 321, "height": 200}
    elif fault == "missing":
        reference["path"] = "references/absent.png"
    plan["visual_references"] = [reference]
    frozen = (
        fixed_file("criteria/execution.json", canonical_json(plan)),
        *request.frozen_inputs[1:],
        image,
    )
    request = replace(request, frozen_inputs=frozen, evaluator_sha256=manifest_digest(frozen[:2]))
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == ("passed" if fault is None else "unavailable")


async def test_cleanup_failure_cannot_claim_complete(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path)
    request = replace(
        request,
        checks=(request.checks[0], {**request.checks[0], "check_id": "second-check"}),
    )
    runner = AsyncMock()
    from ddk.adapters.build_runner import BuildResult

    runner.run.return_value = BuildResult(False, "", "cleanup failed", 125)
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: runner)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    assert not outcome.cleanup_complete
    assert runner.run.call_count == 1
    assert outcome.results[1]["reason_code"] == "cleanup_failed"


@pytest.mark.parametrize(
    "mutation",
    [
        "f.writeFileSync('index.html','altered')",
        "f.chmodSync('index.html',0o600)",
        "f.mkdirSync('src');f.writeFileSync('src/new.js','altered')",
        "f.unlinkSync('index.html')",
        "f.unlinkSync('index.html');f.symlinkSync('missing.html','index.html')",
    ],
)
async def test_source_mutation_blocks_and_retains_only_the_executed_observation(tmp_path, mutation):
    request, original, _ = request_for(
        tmp_path,
        argv=["node", "-e", f"const f=require('fs');{mutation};console.log('observed-first')"],
    )
    request = replace(
        request,
        checks=(
            request.checks[0],
            {
                **request.checks[0],
                "check_id": "second",
                "command_argv": ["node", "-e", "console.log('must-not-execute')"],
            },
        ),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[0]["reason_code"] == "source_changed"
    assert outcome.results[1]["reason_code"] == "source_changed"
    assert outcome.input_tree_sha256 is None
    assert outcome.cleanup_complete
    assert len(outcome.artifacts) == 1
    assert b"observed-first" in outcome.artifacts[0].content
    assert capture_source(original).tree_sha256 == request.snapshot.tree_sha256


@pytest.mark.parametrize("directory", ["dist", ".next", ".turbo", "coverage"])
async def test_only_shared_top_level_build_outputs_are_exempt(tmp_path, directory):
    request, _, _ = request_for(
        tmp_path,
        argv=[
            "node",
            "-e",
            f"const f=require('fs');f.mkdirSync({directory!r});"
            f"f.writeFileSync({directory!r}+'/generated.js','generated')",
        ],
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "passed"
    assert outcome.input_tree_sha256 == request.input_tree_sha256


async def test_request_output_limit_is_cumulative_and_counts_utf8_bytes(tmp_path):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "process.stdout.write('한')"])
    request = replace(
        request,
        limits={**request.limits, "max_output_bytes": 5},
        checks=tuple({**request.checks[0], "check_id": f"check-{number}"} for number in range(3)),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "passed"
    assert outcome.results[1]["reason_code"] == "output_limit"
    assert outcome.results[1]["status"] == "unavailable"
    assert outcome.results[2]["reason_code"] == "output_limit"
    assert len(outcome.artifacts) == 2
    assert outcome.cleanup_complete
    assert outcome.output_bytes == 6


async def test_zero_remaining_output_allows_only_silent_commands(tmp_path):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "process.exit(0)"])
    request = replace(request, limits={**request.limits, "max_output_bytes": 0})
    silent = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert silent.results[0]["status"] == "passed"
    assert silent.output_bytes == 0
    request = replace(
        request,
        checks=(
            {**request.checks[0], "command_argv": ["node", "-e", "process.stdout.write('x')"]},
        ),
    )
    noisy = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert noisy.results[0]["reason_code"] == "output_limit"
    assert noisy.output_bytes == 1


async def test_timeout_output_is_unknown_and_stops_subsequent_checks(tmp_path):
    request, _, _ = request_for(
        tmp_path, argv=["node", "-e", "process.stdout.write('partial');setInterval(()=>{},1000)"]
    )
    first = {**request.checks[0], "required": False, "timeout_ms": 30}
    request = replace(
        request,
        checks=(
            first,
            {
                **first,
                "check_id": "second",
                "required": True,
                "command_argv": ["node", "-e", "console.log('must-not-run')"],
            },
        ),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.output_bytes is None
    assert outcome.cleanup_complete
    assert outcome.results[0]["reason_code"] == "timeout"
    assert outcome.results[1]["reason_code"] == "output_unknown"
    assert len(outcome.artifacts) == 1
    assert b"unknown" in outcome.artifacts[0].content


async def test_failed_preview_start_marks_output_unknown_and_stops_subsequent_checks(tmp_path):
    request, _, _ = request_for(
        tmp_path,
        kind="browser",
        argv=[],
        plan_changes={
            "preview_argv": ["node", "-e", "console.log('한');process.exit(1)", "{port}"]
        },
    )
    first = {**request.checks[0], "required": False, "viewport": {"width": 320, "height": 200}}
    request = replace(
        request,
        checks=(
            first,
            {
                **first,
                "check_id": "second",
                "required": True,
                "kind": "command",
                "viewport": None,
                "command_argv": ["node", "-e", "process.exit(0)"],
            },
        ),
        limits={**request.limits, "max_output_bytes": 1},
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.output_bytes is None
    assert outcome.cleanup_complete
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[1]["reason_code"] == "output_unknown"


async def test_approved_step_timeout_bounds_a_command_with_a_longer_check_timeout(tmp_path):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "setTimeout(()=>process.exit(0),50)"])
    request = replace(request, limits={**request.limits, "step_timeout_ms": 1})
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[0]["reason_code"] == "timeout"
    assert outcome.output_bytes is None
    assert outcome.cleanup_complete


async def test_approved_step_timeout_is_shared_with_preview_and_browser(tmp_path, monkeypatch):
    request, _, _ = request_for(
        tmp_path,
        kind="browser",
        argv=[],
        plan_changes={"preview_argv": ["node", "serve.cjs", "{port}"]},
    )
    request = replace(
        request,
        checks=({**request.checks[0], "viewport": {"width": 320, "height": 200}},),
        limits={**request.limits, "step_timeout_ms": 50},
    )
    from types import SimpleNamespace

    from ddk.adapters.verified_browser import BrowserRun

    preview = AsyncMock()
    preview.start.return_value = SimpleNamespace(
        url="http://127.0.0.1:1234", stop=AsyncMock(), output=lambda: ("", "")
    )
    observed = []

    async def flow(*args, **kwargs):
        observed.append(kwargs["deadline_ns"])
        return BrowserRun(
            {
                "check_id": request.checks[0]["check_id"],
                "status": "unavailable",
                "reason_code": "timeout",
                "artifact_ids": [],
            },
            [],
            True,
        )

    monkeypatch.setattr(
        "ddk.adapters.verified_evaluator.SubprocessPreviewLauncher", lambda: preview
    )
    monkeypatch.setattr("ddk.adapters.verified_evaluator.run_flow", flow)
    before = time.monotonic_ns()
    await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert preview.start.await_args.kwargs["timeout_s"] <= 0.05
    assert before < observed[0]
    assert observed[0] - before < 100_000_000


async def test_request_source_and_artifact_limits_are_applied(tmp_path, monkeypatch):
    request, _, _ = request_for(tmp_path)
    runner = AsyncMock()
    from ddk.adapters.build_runner import BuildResult

    runner.run.return_value = BuildResult(True, "x" * 3000, "", 0)
    monkeypatch.setattr("ddk.adapters.verified_evaluator.SubprocessBuildRunner", lambda: runner)
    too_large = replace(request.snapshot.files[0], content=b"x" * 3000, size_bytes=3000)
    import hashlib

    too_large = replace(too_large, sha256=hashlib.sha256(too_large.content).hexdigest())
    snapshot = SourceSnapshot((too_large,), manifest_digest([too_large]))
    rejected = await VerifiedEvaluator(trusted_local_approved=True).evaluate(
        replace(request, snapshot=snapshot, limits={**request.limits, "max_file_bytes": 2000})
    )
    assert rejected.results[0]["status"] == "unavailable"
    runner.run.assert_not_called()
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(
        replace(request, limits={**request.limits, "max_artifact_bytes": 2000})
    )
    assert outcome.results[0]["reason_code"] == "artifact_limit"
    assert sum(len(artifact.content) for artifact in outcome.artifacts) <= 2000


async def test_timeout_preserves_cancellation_cleanup_failure_and_stops_next_command(
    tmp_path, monkeypatch
):
    request, _, _ = request_for(tmp_path, argv=["node", "-e", "setInterval(()=>{},1000)"])
    first = {**request.checks[0], "timeout_ms": 30}
    request = replace(
        request,
        checks=(
            first,
            {
                **first,
                "check_id": "second",
                "command_argv": ["node", "-e", "console.log('second')"],
            },
        ),
    )
    from ddk.adapters import subprocess_build_runner as implementation

    original_stop, original_start = (
        implementation.stop_owned_process,
        implementation.start_owned_process,
    )
    processes = []

    async def start(*args, **kwargs):
        answer = await original_start(*args, **kwargs)
        processes.append(answer[0])
        return answer

    async def stop_then_report_failure(*args, **kwargs):
        await original_stop(*args, **kwargs)
        raise RuntimeError("synthetic cleanup failure")

    monkeypatch.setattr(implementation, "start_owned_process", start)
    monkeypatch.setattr(implementation, "stop_owned_process", stop_then_report_failure)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert not outcome.cleanup_complete
    assert outcome.results[0]["reason_code"] == "cleanup_failed"
    assert outcome.results[1]["reason_code"] == "cleanup_failed"
    assert len(processes) == 1
    assert processes[0].returncode is not None


@pytest.mark.parametrize("fault", ["source", "output"])
async def test_preview_cleanup_is_followed_by_source_and_output_verification(
    tmp_path, monkeypatch, fault
):
    import hashlib
    from types import SimpleNamespace

    from ddk.adapters.verified_browser import BrowserRun

    request, _, _ = request_for(
        tmp_path,
        kind="browser",
        argv=[],
        plan_changes={"preview_argv": ["node", "serve.cjs", "{port}"]},
    )
    first = {**request.checks[0], "viewport": {"width": 320, "height": 200}}
    request = replace(
        request,
        checks=(first, {**first, "check_id": "second"}),
        limits={**request.limits, "max_output_bytes": 2},
    )
    preview = AsyncMock()

    async def start(command, cwd, **kwargs):
        async def stop():
            if fault == "source":
                (cwd / "index.html").write_text("changed during cleanup")

        return SimpleNamespace(
            url="http://127.0.0.1:1234",
            stop=stop,
            output=lambda: ("한" if fault == "output" else "", ""),
        )

    async def observe(*args, **kwargs):
        payload = b"{}"
        (kwargs["output_dir"] / "observed.json").write_bytes(payload)
        metadata = {
            "artifact_id": "observed",
            "kind": "data",
            "path": "observed.json",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "sensitive": True,
            "public_export_allowed": False,
        }
        result = {
            "check_id": kwargs["check"]["check_id"],
            "phase": "candidate",
            "status": "passed",
            "exit_code": None,
            "executed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "retry_count": 0,
            "duration_ms": 1,
            "reason_code": None,
            "artifact_ids": ["observed"],
            "evidence_origin": "trusted-observer",
            "round_no": 0,
        }
        return BrowserRun(result, [metadata], True)

    preview.start.side_effect = start
    monkeypatch.setattr(
        "ddk.adapters.verified_evaluator.SubprocessPreviewLauncher", lambda: preview
    )
    monkeypatch.setattr("ddk.adapters.verified_evaluator.run_flow", observe)
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    reason = "source_changed" if fault == "source" else "output_limit"
    assert outcome.results[0]["reason_code"] == reason
    assert outcome.results[1]["reason_code"] == reason
    assert outcome.results[0]["status"] == "unavailable"
    assert outcome.results[0]["artifact_ids"] == ["observed"]
    preview.start.assert_awaited_once()
    assert outcome.output_bytes == (3 if fault == "output" else 0)

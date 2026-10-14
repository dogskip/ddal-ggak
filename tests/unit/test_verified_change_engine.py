"""Injected evaluator checks prove orchestration, not actual isolated execution."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.source_snapshot import SnapshotFile, manifest_digest
from ddk.services.verified_change_engine import (
    EvaluationArtifact,
    EvaluationOutcome,
    VerifiedChangeEngine,
)
from ddk.services.verified_change_store import VerifiedChangeStore

DATA = Path(__file__).resolve().parents[2] / "docs/design/verified-change/contract-examples.json"
RUN_ID = "00000000-0000-4000-8000-000000000055"


def fixed_file(path, content, mode=0o644):
    return SnapshotFile(path, content, hashlib.sha256(content).hexdigest(), mode, len(content))


@pytest.fixture
def scenario(tmp_path):
    case = copy.deepcopy(json.loads(DATA.read_text())["valid"][0]["record"])
    source = fixed_file("src/App.tsx", b"before")
    inputs = {"src/App.tsx": b"before"}
    for item in case["inputs"]:
        if item["role"] != "source":
            inputs[item["path"]] = ("fixed:" + item["path"]).encode()
        payload = inputs[item["path"]]
        item.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
    for check in case["checks"]:
        check["definition_sha256"] = next(
            item["sha256"] for item in case["inputs"] if item["path"] == check["definition_path"]
        )
    files = [
        fixed_file(item["path"], inputs[item["path"]], item["mode"]) for item in case["inputs"]
    ]
    case["baseline_tree_sha256"] = manifest_digest([source])
    for role, key in [("criteria", "evaluator_sha256"), ("environment", "environment_sha256")]:
        case[key] = manifest_digest(
            [file for file, item in zip(files, case["inputs"], strict=True) if item["role"] == role]
        )
    baseline = tmp_path / "baseline"
    candidate = tmp_path / "candidate"
    for root, payload in [(baseline, b"before"), (candidate, b"after")]:
        (root / "src").mkdir(parents=True)
        (root / "src/App.tsx").write_bytes(payload)
        (root / "src/App.tsx").chmod(0o644)
    store = VerifiedChangeStore(tmp_path / "records")
    store.publish_case(case, inputs)
    return store, case, baseline, candidate


class Evaluator:
    def __init__(self, *, statuses=None, cleanup=True, metadata=None):
        self.requests = []
        self.statuses = statuses or {}
        self.cleanup = cleanup
        self.metadata = metadata

    async def evaluate(self, request):
        self.requests.append(request)
        ident = request.phase + "-observation"
        artifact = EvaluationArtifact(
            ident,
            "log",
            f"artifacts/{request.phase}/observed.json",
            b"synthetic observer evidence",
            False,
            False,
        )
        results = tuple(
            {
                "check_id": check["check_id"],
                "phase": request.phase,
                "status": self.statuses.get((request.phase, check["check_id"]), "passed"),
                "exit_code": None,
                "executed_count": None,
                "failed_count": None,
                "skipped_count": None,
                "retry_count": 0,
                "duration_ms": 1,
                "reason_code": None,
                "artifact_ids": [ident],
                "evidence_origin": "trusted-observer",
                "round_no": 0,
            }
            for check in request.checks
        )
        value = EvaluationOutcome(
            results,
            (artifact,),
            "isolated",
            request.environment_sha256,
            request.evaluator_sha256,
            request.input_tree_sha256,
            self.cleanup,
        )
        return self.metadata(value) if self.metadata else value


@pytest.mark.asyncio
async def test_approved_limits_reach_the_actual_evaluator_without_shared_mutability(scenario):
    evaluator = Evaluator()
    await verify(scenario, evaluator)
    assert evaluator.requests
    assert evaluator.requests[0].limits == scenario[1]["limits"]
    assert evaluator.requests[0].limits is not scenario[1]["limits"]


@pytest.mark.asyncio
async def test_output_allowance_is_shared_by_baseline_and_candidate(scenario):
    maximum = scenario[1]["limits"]["max_output_bytes"]
    evaluator = Evaluator(metadata=lambda outcome: replace(outcome, output_bytes=maximum))
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert "output_limit" in {action["code"] for action in result["actions"]}
    assert evaluator.requests[1].limits["max_output_bytes"] == 0


async def verify(scenario, evaluator=None, **kwargs):
    store, case, baseline, candidate = scenario
    return await VerifiedChangeEngine(store, evaluator).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=RUN_ID,
        change_requirements={"src/App.tsx": ["R2"]},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_default_execution_fails_closed_without_model_or_original_execution(scenario):
    result = await verify(scenario)
    assert result["decision"] == "blocked"
    assert any(item["code"] == "isolation_unavailable" for item in result["actions"])
    assert result["model_calls"] == []
    assert scenario[3].joinpath("src/App.tsx").read_bytes() == b"after"


@pytest.mark.asyncio
async def test_injected_success_connects_fixed_criteria_source_and_observation(scenario):
    evaluator = Evaluator(statuses={("baseline", "target"): "failed"})
    result = await verify(scenario, evaluator)
    assert result["decision"] == "ready"
    assert result["model_calls"] == []
    assert result["latest_round"] == 0 and len(result["rounds"]) == 1
    assert result["rounds"][0]["changes_sha256"] == record_digest(result["changes"])
    assert [item.phase for item in evaluator.requests] == ["baseline", "candidate"]
    assert evaluator.requests[0].snapshot.files[0].content == b"before"
    assert evaluator.requests[1].snapshot.files[0].content == b"after"
    assert any(item.path == "environment.json" for item in evaluator.requests[0].frozen_inputs)
    assert not hasattr(evaluator.requests[0], "root")
    assert scenario[0].run(RUN_ID) == result


@pytest.mark.asyncio
async def test_baseline_preserve_failure_stops_before_candidate(scenario):
    evaluator = Evaluator(statuses={("baseline", "preserve"): "failed"})
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert result["actions"][0]["code"] == "baseline_failed"
    assert [item.phase for item in evaluator.requests] == ["baseline"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "skipped", "unavailable", "flaky"])
async def test_nonpassing_required_candidate_never_becomes_ready(scenario, status):
    result = await verify(scenario, Evaluator(statuses={("candidate", "target"): status}))
    assert result["decision"] == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("issue", ["empty", "cleanup", "environment", "criteria", "candidate"])
async def test_missing_evidence_or_mismatched_execution_is_blocked(scenario, issue):
    def alter(value):
        if issue == "empty":
            return replace(value, results=())
        if issue == "cleanup":
            return replace(value, cleanup_complete=False)
        if issue == "environment":
            return replace(value, environment_sha256="a" * 64)
        if issue == "criteria":
            return replace(value, evaluator_sha256="b" * 64)
        return replace(value, input_tree_sha256="c" * 64)

    result = await verify(scenario, Evaluator(metadata=alter))
    assert result["decision"] == "blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("issue", ["extra", "delete", "mode", "criteria", "baseline"])
async def test_ambiguous_or_unapproved_candidate_never_runs(scenario, issue):
    _, _, baseline, candidate = scenario
    if issue == "extra":
        (candidate / "extra.tsx").write_bytes(b"new")
    elif issue == "delete":
        (candidate / "src/App.tsx").unlink()
    elif issue == "mode":
        (candidate / "src/App.tsx").chmod(0o600)
    elif issue == "criteria":
        (candidate / "criteria.json").write_bytes(b"changed")
    else:
        (baseline / "src/App.tsx").write_bytes(b"unapproved")
    evaluator = Evaluator()
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert not evaluator.requests


@pytest.mark.asyncio
async def test_same_request_returns_the_saved_result_without_evaluation(scenario):
    evaluator = Evaluator()
    first = await verify(scenario, evaluator)
    assert await verify(scenario, evaluator) == first
    assert len(evaluator.requests) == 2
    scenario[3].joinpath("src/App.tsx").write_bytes(b"different")
    with pytest.raises(ValueError, match="request_conflict"):
        await verify(scenario, evaluator)


@pytest.mark.asyncio
async def test_two_simultaneous_requests_start_one_owned_evaluation(scenario):
    entered = asyncio.Event()
    finish = asyncio.Event()
    evaluator = Evaluator()
    original = evaluator.evaluate
    started_phases = []

    async def wait_for_release(request):
        started_phases.append(request.phase)
        if request.phase == "baseline":
            entered.set()
            await finish.wait()
        return await original(request)

    evaluator.evaluate = wait_for_release
    first = asyncio.create_task(verify(scenario, evaluator))
    await asyncio.wait_for(entered.wait(), 2)
    second_task = asyncio.create_task(verify(scenario, evaluator))
    try:
        await asyncio.sleep(0.05)
        assert started_phases == ["baseline"]
        second = await asyncio.wait_for(second_task, 2)
        assert second["status"] == "running"
    finally:
        finish.set()
        results = await asyncio.gather(first, second_task, return_exceptions=True)
    assert results[0]["decision"] == "ready"
    assert len(evaluator.requests) == 2


@pytest.mark.asyncio
async def test_cancellation_retains_a_terminal_pending_record(scenario):
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    class Waiting:
        async def evaluate(self, request):
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    task = asyncio.create_task(verify(scenario, Waiting()))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cleaned.is_set()
    saved = scenario[0].pending_run(RUN_ID)
    assert saved["status"] == "cancelled" and saved["decision"] is None
    assert saved["model_calls"] == []


@pytest.mark.asyncio
async def test_evaluator_exception_is_a_blocked_result_with_unconfirmed_cleanup(scenario):
    class Broken:
        async def evaluate(self, request):
            raise RuntimeError("synthetic execution failed")

    result = await verify(scenario, Broken())
    assert result["decision"] == "blocked"
    assert result["actions"][0]["code"] == "evaluation_failed"
    assert result["integrity"]["cleanup_complete"] is False


@pytest.mark.asyncio
async def test_criteria_bytes_are_rehashed_after_the_store_check(scenario, monkeypatch):
    import ddk.services.verified_change_engine as module

    original = module.read_regular
    changed = False

    def replace_bytes(path, max_bytes):
        nonlocal changed
        if not changed and path.name == "preserve.json":
            changed = True
            payload = original(path, max_bytes)
            path.write_bytes(b"altered criteria")
            result = original(path, max_bytes)
            path.write_bytes(payload)
            return result
        return original(path, max_bytes)

    monkeypatch.setattr(module, "read_regular", replace_bytes)
    evaluator = Evaluator()
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert result["actions"][0]["code"] == "criteria_changed"
    assert not evaluator.requests


@pytest.mark.asyncio
async def test_explicit_project_criteria_preserve_external_fixed_inputs(
    scenario,
):
    store, case, baseline, candidate = scenario
    payload = (
        store.path_for("case", case["case_id"])
        .joinpath("inputs/criteria/preserve.json")
        .read_bytes()
    )
    for root in (baseline, candidate):
        (root / "tests").mkdir()
        (root / "tests/fixed.json").write_bytes(payload)
    evaluator = Evaluator()
    result = await verify(
        scenario, evaluator, project_inputs={"tests/fixed.json": "criteria/preserve.json"}
    )
    assert result["decision"] == "ready"
    assert evaluator.requests[0].snapshot.files[1].path == "tests/fixed.json"


@pytest.mark.asyncio
async def test_declared_project_criteria_cannot_be_modified_by_candidate(scenario):
    store, case, baseline, candidate = scenario
    payload = (
        store.path_for("case", case["case_id"])
        .joinpath("inputs/criteria/preserve.json")
        .read_bytes()
    )
    for root in (baseline, candidate):
        (root / "tests").mkdir()
        (root / "tests/fixed.json").write_bytes(payload if root == baseline else b"altered")
    result = await verify(
        scenario, Evaluator(), project_inputs={"tests/fixed.json": "criteria/preserve.json"}
    )
    assert result["decision"] == "blocked"
    assert result["actions"][0]["code"] == "criteria_changed"


def revised_case(scenario, change):
    store, previous, baseline, candidate = scenario
    case = copy.deepcopy(previous)
    case["case_id"] = "00000000-0000-4000-8000-000000000099"
    change(case)
    inputs = {
        item["path"]: store.path_for("case", previous["case_id"])
        .joinpath("inputs", item["path"])
        .read_bytes()
        for item in previous["inputs"]
    }
    store.publish_case(case, inputs)
    return store, case, baseline, candidate


@pytest.mark.asyncio
async def test_execution_uses_one_monotonic_deadline_and_cancels_the_evaluator(
    scenario, monkeypatch
):
    cleaned = asyncio.Event()
    elapsed_ns = 0
    monkeypatch.setattr("ddk.services.verified_change_engine.time.monotonic_ns", lambda: elapsed_ns)

    class Slow:
        async def evaluate(self, request):
            nonlocal elapsed_ns
            elapsed_ns = 1_000_000_000
            try:
                await asyncio.sleep(10)
            finally:
                cleaned.set()

    updated = revised_case(
        scenario, lambda case: case["limits"].update(run_timeout_ms=80, cleanup_timeout_ms=20)
    )
    result = await asyncio.wait_for(verify(updated, Slow()), 2)
    assert result["decision"] == "blocked"
    assert result["actions"][0]["code"] == "run_timeout"
    assert result["integrity"]["cleanup_complete"] is False
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_cancel_callback_keeps_pending_state_without_resuming_work(scenario):
    stop = False
    cleaned = asyncio.Event()

    class Waiting:
        async def evaluate(self, request):
            nonlocal stop
            stop = True
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

    result = await asyncio.wait_for(verify(scenario, Waiting(), cancelled=lambda: stop), 2)
    assert result["status"] == "cancelled" and result["decision"] is None
    assert cleaned.is_set()
    assert scenario[0].pending_run(RUN_ID) == result


@pytest.mark.asyncio
async def test_empty_required_baseline_observation_stops_before_candidate(scenario):
    evaluator = Evaluator(
        metadata=lambda value: replace(
            value,
            results=tuple(
                {**item, "artifact_ids": []} if item["check_id"] == "preserve" else item
                for item in value.results
            ),
        )
    )
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert [request.phase for request in evaluator.requests] == ["baseline"]


@pytest.mark.asyncio
async def test_mapping_omission_reports_the_path_and_required_input(scenario):
    store, case, baseline, candidate = scenario
    result = await VerifiedChangeEngine(store, Evaluator()).verify(
        case["case_id"], baseline=baseline, candidate=candidate, run_id=RUN_ID
    )
    action = result["actions"][0]
    assert action["code"] == "ambiguous_change_requirements"
    assert action["target"] == "src/App.tsx"
    assert "change_requirements[path]" in action["message"]


@pytest.mark.asyncio
async def test_optional_candidate_issue_is_a_manual_review(scenario):
    def optional(case):
        extra = copy.deepcopy(case["checks"][0])
        extra.update(check_id="advisory", required=False, role="target")
        case["checks"].append(extra)

    updated = revised_case(scenario, optional)
    result = await verify(updated, Evaluator(statuses={("candidate", "advisory"): "unavailable"}))
    assert result["decision"] == "manual-review"
    assert any(action["target"] == "advisory" for action in result["actions"])


@pytest.mark.asyncio
async def test_an_unknown_assurance_value_is_rejected_as_a_result(scenario):
    result = await verify(
        scenario, Evaluator(metadata=lambda value: replace(value, assurance="unverified"))
    )
    assert result["decision"] == "blocked"


@pytest.mark.asyncio
async def test_another_round_cannot_supply_this_verification_result(scenario):
    evaluator = Evaluator(
        metadata=lambda value: replace(
            value, results=tuple({**item, "round_no": 1} for item in value.results)
        )
    )
    result = await verify(scenario, evaluator)
    assert result["decision"] == "blocked"
    assert [request.phase for request in evaluator.requests] == ["baseline"]

"""A repair owns one budget and cannot rewrite approved criteria or originals."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

from ddk.services.verified_budget import ProviderResult, ProviderUsage
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_repair import RepairReply, VerifiedRepairEngine
from tests.unit.test_verified_budget import price
from tests.unit.test_verified_change_engine import RUN_ID, Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario

REPAIR_ID = "00000000-0000-4000-8000-000000000077"


class ObservingEvaluator(Evaluator):
    async def evaluate(self, request):
        content = next(
            item.content for item in request.snapshot.files if item.path == "src/App.tsx"
        )
        self.statuses = {
            ("candidate", check["check_id"]): "failed"
            for check in request.checks
            if check["required"] and check["role"] == "target" and content != b"fixed"
        }
        return replace(await super().evaluate(request), output_bytes=3)


@pytest.fixture
async def blocked(scenario):
    store, case, baseline, candidate = scenario
    observer = ObservingEvaluator()
    run = await VerifiedChangeEngine(store, observer).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=RUN_ID,
        change_requirements={"src/App.tsx": [case["requirements"][-1]["requirement_id"]]},
    )
    assert run["decision"] == "blocked"
    return scenario, run


_USAGE = ProviderUsage(1, 1, 0)


def answer(content="fixed", *, path="src/App.tsx", usage=_USAGE, truncated=False):
    payload = json.dumps({"files": [{"path": path, "content": content}]})
    return ProviderResult(
        RepairReply(payload, truncated, len(payload.encode())),
        usage,
        "anthropic",
        "claude-sonnet-5-5",
    )


async def repair(blocked, provider, *, observer=None, run_id=REPAIR_ID, **options):
    (store, _, baseline, candidate), source = blocked
    return await VerifiedRepairEngine(store, observer or ObservingEvaluator(), provider).repair(
        source["run_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=run_id,
        price=price(source),
        input_limit=4096,
        output_limit=4096,
        **options,
    )


async def test_repair_reserves_before_provider_and_rechecks_one_request(blocked):
    (store, case, baseline, candidate), source = blocked
    seen = []
    observer = ObservingEvaluator()

    async def provider(request):
        current = store.pending_run(REPAIR_ID)
        assert current["model_calls"][-1]["state"] == "reserved"
        assert current["operation"] == "repair" and current["source_run_id"] == RUN_ID
        seen.append(request)
        return answer()

    result = await repair(blocked, provider, observer=observer)
    assert result["decision"] == "ready", result["actions"]
    assert [r["round_no"] for r in result["rounds"]] == [0, 1]
    assert result["latest_round"] == 1
    assert len(result["model_calls"]) == len(seen) == 1
    assert result["model_calls"][0]["round_no"] == 0
    assert result["model_calls"][0]["state"] == "settled"
    assert [r.phase for r in observer.requests] == ["baseline", "candidate", "candidate"]
    assert len({r.deadline_ns for r in observer.requests}) == 1
    assert [r.limits["max_output_bytes"] for r in observer.requests[:2]] == [
        case["limits"]["max_output_bytes"],
        case["limits"]["max_output_bytes"] - 3,
    ]
    assert (
        observer.requests[2].limits["max_output_bytes"]
        < observer.requests[1].limits["max_output_bytes"] - 3
    )
    assert (baseline / "src/App.tsx").read_bytes() == b"before"
    assert (candidate / "src/App.tsx").read_bytes() == b"after"
    assert store.run(RUN_ID) == source
    assert store.case(case["case_id"]) == case
    assert store.run(REPAIR_ID) == result
    assert len({a["artifact_id"] for a in result["artifacts"]}) == len(result["artifacts"])
    assert await repair(blocked, provider, observer=observer) == result
    assert len(seen) == 1


@pytest.mark.parametrize(
    "proposal,code",
    [
        (answer("after"), "repair_no_progress"),
        (answer(path="package.json"), "repair_outside_scope"),
        (answer(""), "repair_response_invalid"),
        (answer(truncated=True), "repair_response_incomplete"),
        (answer(usage=None), "cost_unknown"),
    ],
)
async def test_unsafe_or_unaccounted_reply_stops_without_another_call(blocked, proposal, code):
    calls = []

    async def provider(request):
        calls.append(request)
        return proposal

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert code in [a["code"] for a in result["actions"]]
    assert len(calls) == 1


async def test_two_repairs_share_reservations_and_retain_previous_evidence(blocked):
    calls = []

    async def provider(request):
        calls.append(request)
        return answer("not-yet" if len(calls) == 1 else "fixed")

    result = await repair(blocked, provider)
    assert result["decision"] == "ready", result["actions"]
    assert [c["attempt_no"] for c in result["model_calls"]] == [1, 2]
    assert [c["round_no"] for c in result["model_calls"]] == [0, 1]
    assert result["latest_round"] == 2
    assert {r["round_no"] for r in result["results"]} == {0, 1, 2}


async def test_provider_failure_retains_unknown_and_same_id_does_not_resume(blocked):
    (store, _, _, _), _ = blocked
    calls = []

    async def provider(request):
        calls.append(request)
        raise RuntimeError("private provider details")

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert result["model_calls"][0]["state"] == "unknown"
    assert "private provider details" not in json.dumps(result)
    assert await repair(blocked, provider) == result
    assert len(calls) == 1
    assert store.status(REPAIR_ID) == result


async def test_cancelled_provider_is_saved_and_never_resumed(blocked):
    (store, _, _, _), _ = blocked
    started = asyncio.Event()

    async def provider(request):
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(repair(blocked, provider))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    saved = store.status(REPAIR_ID)
    assert saved["status"] == "cancelled"
    assert saved["model_calls"][0]["state"] == "unknown"
    assert await repair(blocked, provider) == saved


async def test_candidate_change_after_source_run_is_rejected_before_provider(blocked):
    (_, _, _, candidate), _ = blocked
    (candidate / "src/App.tsx").write_bytes(b"external edit")

    async def provider(request):
        pytest.fail("source mismatch must not authorize a provider")

    with pytest.raises(ValueError, match="source_candidate_mismatch"):
        await repair(blocked, provider)


async def test_provider_cannot_change_criteria_during_a_request(blocked):
    (store, case, _, _), _ = blocked

    async def provider(request):
        fixed = next(item for item in case["inputs"] if item["role"] == "criteria")
        (store.path_for("case", case["case_id"]) / "inputs" / fixed["path"]).write_bytes(b"changed")
        return answer()

    with pytest.raises(ValueError):
        await repair(blocked, provider)
    assert not (store.path_for("run", REPAIR_ID) / "run.json").exists()


async def test_input_limit_is_checked_before_reserving_or_calling(blocked):
    (store, _, baseline, candidate), source = blocked

    async def provider(request):
        pytest.fail("oversized context must not reach provider")

    result = await VerifiedRepairEngine(store, ObservingEvaluator(), provider).repair(
        source["run_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=REPAIR_ID,
        price=price(source),
        input_limit=1,
        output_limit=512,
    )
    assert result["decision"] == "blocked"
    assert result["model_calls"] == []
    assert result["actions"][-1]["code"] == "repair_input_limit"


async def test_verified_service_requires_explicit_provider_authorization(blocked):
    from ddk.services.verified_change_service import VerifiedChangeService

    (store, _, baseline, candidate), source = blocked

    async def provider(request):
        return answer()

    service = VerifiedChangeService(store.repository, evaluator=ObservingEvaluator())
    options = {
        "baseline": baseline,
        "candidate": candidate,
        "run_id": REPAIR_ID,
        "price": price(source),
        "input_limit": 4096,
        "output_limit": 512,
        "provider": provider,
    }
    with pytest.raises(ValueError, match="provider_confirmation_required"):
        await service.repair(source["run_id"], **options)
    assert not store.path_for("run", REPAIR_ID).exists()
    result = await service.repair(source["run_id"], provider_approved=True, **options)
    assert result["decision"] == "ready"


async def test_a_new_request_cannot_bypass_unknown_cost_from_previous_run(blocked):
    calls = []

    async def provider(request):
        calls.append(request)
        return answer(usage=None)

    first = await repair(blocked, provider)
    assert first["actions"][-1]["code"] == "cost_unknown"
    second = await repair(blocked, provider, run_id="00000000-0000-4000-8000-000000000078")
    assert second["decision"] == "blocked"
    assert second["actions"][-1]["code"] == "cost_unknown"
    assert len(calls) == 1


@pytest.mark.parametrize(
    "content",
    [
        '{"files":[],"decision":"ready"}',
        '{"files":[{"path":"src/App.tsx","content":"ok"},{"path":"src/App.tsx","content":"other"}]}',
        '{"files":[],"files":[]}',
        '{"files":[42]}',
    ],
)
async def test_malformed_proposal_cannot_change_the_candidate(blocked, content):
    async def provider(request):
        return replace(answer(), value=RepairReply(content, output_bytes=len(content.encode())))

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "repair_response_invalid"


async def test_invalid_utf8_reply_is_a_final_blocked_result(blocked):
    async def provider(request):
        return replace(answer(), value=RepairReply("\ud800"))

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "repair_response_invalid"


async def test_candidate_cycle_stops_in_the_same_request(blocked):
    calls = []

    async def provider(request):
        calls.append(request)
        return answer("middle" if len(calls) == 1 else "after")

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "repair_no_progress"
    assert len(calls) == 2
    assert [r["round_no"] for r in result["rounds"]] == [0, 1]


async def test_already_passing_candidate_needs_no_model_call(blocked):
    async def provider(request):
        pytest.fail("passing candidate must not call a model")

    result = await repair(blocked, provider, observer=Evaluator())
    assert result["decision"] == "ready", result["actions"]
    assert result["model_calls"] == []
    assert result["latest_round"] == 0


async def test_output_is_shared_by_model_replies_and_all_rechecks(blocked):
    (store, case, _, _), source = blocked
    import copy
    from uuid import uuid4

    approved = copy.deepcopy(case)
    approved.update(case_id=str(uuid4()), supersedes_case_id=case["case_id"])
    approved["limits"]["max_output_bytes"] = 10
    payloads = {
        item["path"]: (
            store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    store.publish_case(approved, payloads)
    (_, _, baseline, candidate), _ = blocked
    source = await VerifiedChangeEngine(store, ObservingEvaluator()).verify(
        approved["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": source["changes"][0]["requirement_ids"]},
    )
    observer = ObservingEvaluator()

    async def provider(request):
        return answer()

    result = await repair(
        ((store, approved, baseline, candidate), source), provider, observer=observer
    )
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "output_limit"
    assert len(observer.requests) == 2


async def test_ready_result_cannot_contain_unknown_provider_cost(blocked):
    from ddk.models.verified_change import ContractError, validate_record

    (store, case, _, _), source = blocked

    async def provider(request):
        return answer()

    result = await repair(blocked, provider)
    assert result["decision"] == "ready"
    result["model_calls"][0].update(state="unknown", calculated_micro_usd=None)
    with pytest.raises(ContractError, match="cost_unknown"):
        validate_record(result, {case["case_id"]: case}, {source["run_id"]: source})


async def test_source_reference_depth_is_bounded_without_python_recursion_failure(blocked):
    import copy
    from uuid import uuid4

    from ddk.models.verified_change import canonical_json

    (store, _, _, _), source = blocked
    parent = source["run_id"]
    for _ in range(33):
        record = copy.deepcopy(source)
        record.update(
            run_id=str(uuid4()),
            source_run_id=parent,
            operation="repair",
            artifacts=[],
            changes=[],
            results=[],
            model_calls=[],
        )
        directory = store.path_for("run", record["run_id"])
        directory.mkdir()
        manifest = directory / "run.json"
        manifest.write_bytes(canonical_json(record))
        manifest.chmod(0o600)
        parent = record["run_id"]
    with pytest.raises(ValueError, match="source_run_depth"):
        store.run(parent)


async def with_limits(blocked, **limits):
    import copy
    from uuid import uuid4

    (store, case, baseline, candidate), previous = blocked
    approved = copy.deepcopy(case)
    approved.update(case_id=str(uuid4()), supersedes_case_id=case["case_id"])
    approved["limits"].update(limits)
    payloads = {
        item["path"]: (
            store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    store.publish_case(approved, payloads)
    source = await VerifiedChangeEngine(store, ObservingEvaluator()).verify(
        approved["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": previous["changes"][0]["requirement_ids"]},
    )
    return (store, approved, baseline, candidate), source


@pytest.mark.parametrize(
    "limits,code,attempts",
    [
        ({"max_fix_attempts": 0}, "fix_limit", 0),
        ({"max_fix_attempts": 1}, "fix_limit", 1),
        ({"max_provider_requests": 0}, "request_limit", 0),
        ({"max_provider_requests": 1}, "request_limit", 1),
        ({"budget_micro_usd": 0}, "cost_reservation_limit", 0),
        ({"budget_micro_usd": 3}, "cost_reservation_limit", 1),
    ],
)
async def test_request_limits_stop_before_the_next_attempt(blocked, limits, code, attempts):
    variant = await with_limits(blocked, **limits)
    calls = []

    async def provider(request):
        calls.append(request)
        return answer("still wrong")

    result = await repair(variant, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == code
    assert len(calls) == attempts
    assert len(result["model_calls"]) == attempts


async def test_failed_cleanup_never_authorizes_provider_work(blocked):
    async def provider(request):
        pytest.fail("cleanup failure must stop before proposal")

    result = await repair(blocked, provider, observer=Evaluator(cleanup=False))
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "cleanup_failed"
    assert result["model_calls"] == []


async def test_replay_with_changed_price_is_a_conflict(blocked):
    (store, _, baseline, candidate), source = blocked
    calls = []

    async def provider(request):
        calls.append(request)
        return answer()

    await repair(blocked, provider)
    with pytest.raises(ValueError, match="request_conflict"):
        await VerifiedRepairEngine(store, ObservingEvaluator(), provider).repair(
            RUN_ID,
            baseline=baseline,
            candidate=candidate,
            run_id=REPAIR_ID,
            price=price(source, input_micro_usd_per_million=2),
            input_limit=4096,
            output_limit=4096,
        )
    assert len(calls) == 1


async def test_inline_credentials_are_redacted_from_the_provider_context(blocked):
    import copy
    from uuid import uuid4

    (store, case, baseline, candidate), previous = blocked
    approved = copy.deepcopy(case)
    approved.update(
        case_id=str(uuid4()),
        supersedes_case_id=case["case_id"],
        request="Use sk-ant-abcdefghijklmnopqrstuvwxyz1234567890 safely",
    )
    payloads = {
        item["path"]: (
            store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    store.publish_case(approved, payloads)
    source = await VerifiedChangeEngine(store, ObservingEvaluator()).verify(
        approved["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": previous["changes"][0]["requirement_ids"]},
    )
    seen = []

    async def provider(request):
        seen.append(request.prompt)
        return answer()

    result = await repair(((store, approved, baseline, candidate), source), provider)
    assert result["decision"] == "ready"
    assert "sk-ant-abcdefghijklmnopqrstuvwxyz1234567890" not in seen[0]


async def test_replay_with_changed_candidate_is_a_request_conflict(blocked):
    (_, _, _, candidate), _ = blocked

    async def provider(request):
        return answer()

    await repair(blocked, provider)
    (candidate / "src/App.tsx").write_bytes(b"other candidate")
    with pytest.raises(ValueError, match="request_conflict"):
        await repair(blocked, provider)


async def test_provider_receives_redacted_failure_diagnostics(blocked):
    class DiagnosingEvaluator(ObservingEvaluator):
        async def evaluate(self, request):
            outcome = await super().evaluate(request)
            return replace(
                outcome,
                artifacts=tuple(
                    replace(item, content=b"Type error in src/App.tsx: expected string, got number")
                    for item in outcome.artifacts
                ),
            )

    prompts = []

    async def provider(request):
        prompts.append(request.prompt)
        return answer()

    result = await repair(blocked, provider, observer=DiagnosingEvaluator())
    assert result["decision"] == "ready"
    assert "expected string, got number" in prompts[0]


async def test_a_source_without_approved_changes_does_not_spend_provider_budget(blocked):
    from uuid import uuid4

    (store, case, baseline, candidate), _ = blocked
    (candidate / "src/App.tsx").write_bytes(b"before")
    source = await VerifiedChangeEngine(store, ObservingEvaluator()).verify(
        case["case_id"], baseline=baseline, candidate=candidate, run_id=str(uuid4())
    )
    assert source["decision"] == "blocked" and source["changes"] == []

    async def provider(request):
        pytest.fail("there are no approved changed paths")

    result = await repair(((store, case, baseline, candidate), source), provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "repair_scope_empty"
    assert result["model_calls"] == []


@pytest.mark.parametrize(("allowance", "phase_count"), [(3, 1), (6, 2)])
async def test_exhausted_output_stops_before_another_provider_attempt(
    blocked, allowance, phase_count
):
    variant = await with_limits(blocked, max_output_bytes=allowance)
    observer = ObservingEvaluator()

    async def provider(request):
        pytest.fail("output allowance is already exhausted")

    result = await repair(variant, provider, observer=observer)
    assert len(observer.requests) == phase_count
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "output_limit"
    assert result["model_calls"] == []


async def test_provider_reply_is_retained_as_private_evidence(blocked):
    (store, _, _, _), _ = blocked

    async def provider(request):
        return answer()

    result = await repair(blocked, provider)
    proposal = [a for a in result["artifacts"] if a["path"].startswith("artifacts/proposals/")]
    assert len(proposal) == 1
    assert proposal[0]["sensitive"] and not proposal[0]["public_export_allowed"]
    assert json.loads((store.path_for("run", REPAIR_ID) / proposal[0]["path"]).read_text())["files"]


async def test_oversized_reply_evidence_finishes_blocked_with_settled_usage(blocked):
    variant = await with_limits(blocked, max_artifact_bytes=4096)

    async def provider(request):
        return answer("x" * 6000)

    result = await repair(variant, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "artifact_limit"
    assert result["model_calls"][0]["state"] == "settled"
    assert sum(a["size_bytes"] for a in result["artifacts"]) <= 4096


async def test_provider_reasoning_and_metadata_bytes_consume_the_same_output_allowance(blocked):
    variant = await with_limits(blocked, max_output_bytes=2048)

    async def provider(request):
        value = answer()
        return replace(value, value=replace(value.value, output_bytes=4096))

    observer = ObservingEvaluator()
    result = await repair(variant, provider, observer=observer)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "output_limit"
    assert len(observer.requests) == 2
    assert result["model_calls"][0]["state"] == "settled"

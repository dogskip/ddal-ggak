"""Durable reservations precede a single provider attempt and survive uncertainty."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.durable_files import OwnedLock, read_regular
from ddk.services.verified_budget import (
    BudgetError,
    ProviderResult,
    ProviderUsage,
    RunBudget,
    VerifiedPrice,
)
from ddk.services.verified_change_store import VerifiedChangeStore

EXAMPLES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tests/fixtures/verified-change/contract-examples.json"
    ).read_text()
)


@pytest.fixture
def prepared(tmp_path):
    case = copy.deepcopy(EXAMPLES["valid"][0]["record"])
    inputs = {}
    for i, item in enumerate(case["inputs"]):
        payload = f"input-{i}".encode()
        item.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
        inputs[item["path"]] = payload
    for check in case["checks"]:
        check["definition_sha256"] = next(
            i["sha256"] for i in case["inputs"] if i["path"] == check["definition_path"]
        )
    run = copy.deepcopy(EXAMPLES["valid"][1]["record"])
    run.update(
        status="prepared",
        decision=None,
        finished_at=None,
        duration_ms=None,
        operation="generation",
        source_run_id=None,
        results=[],
        artifacts=[],
        model_calls=[],
        changes=[],
        case_sha256=record_digest(case),
    )
    run["rounds"][0]["changes_sha256"] = record_digest([])
    return tmp_path, case, inputs, run


def setup(prepared, **limits):
    directory, case, inputs, run = prepared
    case["limits"].update(limits)
    run["case_sha256"] = record_digest(case)
    store = VerifiedChangeStore(directory)
    store.publish_case(case, inputs)
    return store, run


def price(run, **changes):
    return replace(
        VerifiedPrice(
            provider="anthropic",
            model="claude-sonnet-5-5",
            input_micro_usd_per_million=1,
            output_micro_usd_per_million=1,
            extra_max_micro_usd=2,
            source_url="https://example.test/verified-price",
            verified_at="2026-10-14T03:00:00Z",
            evaluator_sha256=run["evaluator_sha256"],
        ),
        **changes,
    )


_DEFAULT_USAGE = ProviderUsage(1, 1, 0)


def result(usage=_DEFAULT_USAGE):
    return ProviderResult(
        value="response", usage=usage, provider="anthropic", model="claude-sonnet-5-5"
    )


async def successful():
    return result()


def new_run(run):
    new = copy.deepcopy(run)
    new["run_id"] = str(uuid.uuid4())
    return new


async def call(budget, run, provider=successful, **kwargs):
    return await budget.call(
        0, price=price(run), input_limit=10, output_limit=10, provider=provider, **kwargs
    )


def artifact_json(store, run, artifact_id):
    item = next(a for a in run["artifacts"] if a["artifact_id"] == artifact_id)
    return json.loads(
        read_regular(store.path_for("run", run["run_id"]) / item["path"], item["size_bytes"])
    )


async def test_reservation_and_verified_price_are_durable_before_one_attempt(prepared):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    attempts = []

    async def provider():
        stored = store.pending_run(run["run_id"])
        reservation = stored["model_calls"][0]
        assert reservation["state"] == "reserved"
        assert reservation["reserved_micro_usd"] == 3
        fixed = artifact_json(store, stored, reservation["price_artifact_id"])
        assert fixed["price"]["source_url"] == "https://example.test/verified-price"
        assert fixed["price"]["verified_at"] == "2026-10-14T03:00:00Z"
        assert fixed["price"]["evaluator_sha256"] == run["evaluator_sha256"]
        assert (
            fixed["budget_code_sha256"]
            == hashlib.sha256(
                Path(__import__(RunBudget.__module__, fromlist=["__file__"]).__file__).read_bytes()
            ).hexdigest()
        )
        assert (store.base_path / f"locks/model/{run['case_id']}.lock").is_file()
        attempts.append(1)
        return result()

    outcome = await call(budget, run, provider)
    assert attempts == [1]
    assert outcome.value == "response"
    assert outcome.call_record["state"] == "settled"
    assert outcome.call_record["calculated_micro_usd"] == 1
    assert outcome.call_record["completed_at"]
    assert not outcome.blocked
    assert store.pending_run(run["run_id"])["model_calls"] == [outcome.call_record]
    assert not (store.base_path / f"locks/model/{run['case_id']}.lock").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"provider": "unverified"},
        {"model": "claude-from-the-future"},
        {"model": "claude-sonnet-5-5-latest"},
        {"source_url": ""},
        {"verified_at": ""},
        {"evaluator_sha256": "a" * 64},
        {"input_micro_usd_per_million": True},
        {"extra_max_micro_usd": -1},
    ],
)
async def test_unverified_price_never_invokes_or_reserves(prepared, changes):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    attempts = []

    async def provider():
        attempts.append(1)
        return result()

    with pytest.raises(BudgetError, match="price_unavailable"):
        await budget.call(
            0, price=price(run, **changes), input_limit=10, output_limit=10, provider=provider
        )
    assert attempts == []
    assert store.pending_run(run["run_id"])["model_calls"] == []


@pytest.mark.parametrize(
    "usage", [None, ProviderUsage(None, 1, 0), ProviderUsage(1, None, 0), ProviderUsage(1, 1, None)]
)
async def test_missing_usage_keeps_full_unknown_and_blocks_other_runs(prepared, usage):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)

    async def provider():
        return result(usage)

    outcome = await call(budget, run, provider)
    assert outcome.call_record["state"] == "unknown"
    assert outcome.call_record["reserved_micro_usd"] == 3
    assert outcome.call_record["calculated_micro_usd"] is None
    assert store.pending_run(run["run_id"])["decision"] is None
    for other in (budget, RunBudget.start(store, new_run(run))):
        with pytest.raises(BudgetError, match="cost_unknown"):
            await call(other, run)


async def test_explicit_zero_usage_is_settled(prepared):
    store, run = setup(prepared)

    async def provider():
        return result(ProviderUsage(0, 0, 0))

    outcome = await call(RunBudget.start(store, run), run, provider)
    assert outcome.call_record["state"] == "settled"
    assert outcome.call_record["calculated_micro_usd"] == 0


@pytest.mark.parametrize("error", [RuntimeError("provider unavailable"), asyncio.CancelledError()])
async def test_provider_error_or_cancellation_never_retries_or_releases_reservation(
    prepared, error
):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    attempts = []

    async def provider():
        attempts.append(1)
        raise error

    with pytest.raises(type(error)):
        await call(budget, run, provider)
    assert attempts == [1]
    saved = store.pending_run(run["run_id"])["model_calls"][0]
    assert saved["state"] == "unknown"
    assert saved["reserved_micro_usd"] == 3
    assert saved["calculated_micro_usd"] is None
    with pytest.raises(BudgetError, match="cost_unknown"):
        await call(budget, run)


async def test_abrupt_stop_after_reservation_retains_owner_lock_and_reservation(prepared):
    class ProcessStopped(BaseException):
        pass

    store, run = setup(prepared)

    async def provider():
        raise ProcessStopped()

    with pytest.raises(ProcessStopped):
        await call(RunBudget.start(store, run), run, provider)
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "reserved"
    assert (store.base_path / f"locks/model/{run['case_id']}.lock").is_file()
    with pytest.raises(BudgetError, match="budget_resume_forbidden"):
        RunBudget.start(store, run)


async def test_failed_durable_reservation_never_invokes_and_keeps_lock(prepared):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    attempts = []

    async def provider():
        attempts.append(1)
        return result()

    with (
        patch.object(store, "save_pending", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        await call(budget, run, provider)
    assert attempts == []
    assert (store.base_path / f"locks/model/{run['case_id']}.lock").is_file()
    assert list((store.path_for("run", run["run_id"]) / "artifacts/prices").iterdir())


async def test_case_lock_serializes_different_runs_through_settlement(prepared):
    store, run = setup(prepared)
    first = RunBudget.start(store, run)
    second = RunBudget.start(store, new_run(run))
    entered, release = asyncio.Event(), asyncio.Event()
    events = []

    async def a():
        events.append("a-start")
        entered.set()
        await release.wait()
        events.append("a-end")
        return result()

    async def b():
        assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "settled"
        events.append("b")
        return result()

    task_a = asyncio.create_task(call(first, run, a))
    await asyncio.wait_for(entered.wait(), 2)
    task_b = asyncio.create_task(call(second, run, b))
    await asyncio.sleep(0.02)
    assert events == ["a-start"]
    release.set()
    await asyncio.wait_for(asyncio.gather(task_a, task_b), 3)
    assert events == ["a-start", "a-end", "b"]


@pytest.mark.parametrize(
    "limit_name,limit_value,code",
    [
        ("max_provider_requests", 1, "request_limit"),
        ("budget_micro_usd", 3, "cost_reservation_limit"),
    ],
)
async def test_limits_span_all_rounds_and_reconstruction_is_forbidden(
    prepared, limit_name, limit_value, code
):
    store, run = setup(prepared, **{limit_name: limit_value})
    budget = RunBudget.start(store, run)
    await call(budget, run)
    current = store.pending_run(run["run_id"])
    next_round = copy.deepcopy(current["rounds"][0])
    next_round.update(round_no=1)
    current["rounds"].append(next_round)
    current["latest_round"] = 1
    store.save_pending(current)
    with pytest.raises(BudgetError, match=code):
        await budget.call(1, price=price(run), input_limit=10, output_limit=10, provider=successful)
    with pytest.raises(BudgetError, match="budget_resume_forbidden"):
        RunBudget.start(store, run)


async def test_monotonic_deadline_spans_rounds_and_lock_wait(prepared):
    store, run = setup(prepared, run_timeout_ms=100)
    now = [1_000_000_000]
    budget = RunBudget.start(store, run, clock_ns=lambda: now[0])
    lock = OwnedLock(
        store.base_path / f"locks/model/{run['case_id']}.lock", run["run_id"]
    ).acquire()
    task = asyncio.create_task(call(budget, run))
    await asyncio.sleep(0.02)
    now[0] += 101_000_000
    with pytest.raises(BudgetError, match="run_timeout"):
        await asyncio.wait_for(task, 1)
    lock.release()
    with pytest.raises(BudgetError, match="run_timeout"):
        await call(budget, run)
    assert store.pending_run(run["run_id"])["model_calls"] == []


async def test_provider_deadline_cancels_once_and_retains_unknown(prepared):
    store, run = setup(prepared, step_timeout_ms=20)
    attempts = []

    async def provider():
        attempts.append(1)
        await asyncio.Event().wait()
        return result()

    with pytest.raises(BudgetError, match="step_timeout"):
        await call(RunBudget.start(store, run, clock_ns=lambda: 0), run, provider)
    assert attempts == [1]
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "unknown"


@pytest.mark.parametrize(
    "usage,code",
    [
        (ProviderUsage(10, 10, 20), "cost_reservation_exceeded"),
        (ProviderUsage(11, 1, 0), "provider_request_limit_exceeded"),
    ],
)
async def test_over_limit_observation_is_preserved_and_blocks_additional_calls(
    prepared, usage, code
):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)

    async def provider():
        return result(usage)

    outcome = await call(budget, run, provider)
    assert outcome.blocked
    assert outcome.call_record["input_tokens"] == usage.input_tokens
    assert outcome.call_record["output_tokens"] == usage.output_tokens
    expected = (
        usage.input_tokens + usage.output_tokens + 999_999
    ) // 1_000_000 + usage.extra_micro_usd
    assert outcome.call_record["calculated_micro_usd"] == expected
    saved = store.run(run["run_id"])
    assert outcome.run_record == saved
    assert saved["status"] == "completed"
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "reserved"
    assert saved["decision"] == "blocked"
    assert any(a["code"] == code for a in saved["actions"])
    with pytest.raises(BudgetError, match="budget_blocked"):
        await call(budget, run)


@pytest.mark.parametrize("damage", ["corrupt", "orphan", "unreferenced-price"])
async def test_corrupt_or_orphan_history_fails_closed(prepared, damage):
    store, run = setup(prepared)
    first = RunBudget.start(store, run)
    await call(first, run)
    base = store.path_for("run", run["run_id"])
    if damage == "corrupt":
        (base / ".pending/run.json").write_bytes(b"broken")
    elif damage == "orphan":
        (store.base_path / "runs" / str(uuid.uuid4())).mkdir()
    else:
        (base / "artifacts/prices/orphan.json").write_bytes(b"{}")
    second = RunBudget.start(store, new_run(run))
    with pytest.raises(BudgetError, match="budget_history_invalid"):
        await call(second, run)


async def test_completed_unknown_also_blocks_other_run(prepared):
    store, run = setup(prepared)
    first = RunBudget.start(store, run)

    async def provider():
        return result(None)

    await call(first, run, provider)
    completed = store.pending_run(run["run_id"])
    completed.update(
        status="completed", decision="blocked", finished_at="2026-10-14T03:00:01Z", duration_ms=1
    )
    payloads = {
        a["path"]: read_regular(store.path_for("run", run["run_id"]) / a["path"], a["size_bytes"])
        for a in completed["artifacts"]
    }
    store.publish_run(completed, payloads)
    with pytest.raises(BudgetError, match="cost_unknown"):
        await call(RunBudget.start(store, new_run(run)), run)


async def test_model_budget_does_not_acquire_or_modify_independent_apply_lock(prepared):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    lock = OwnedLock(store.base_path / "locks/apply.lock", run["run_id"]).acquire()
    try:
        before = read_regular(lock.path, 4096)
        await call(budget, run)
        assert read_regular(lock.path, 4096) == before
        assert not (store.base_path / f"locks/model/{run['case_id']}.lock").exists()
    finally:
        lock.release()


async def test_observed_token_overrun_blocks_even_when_extra_usage_is_missing(prepared):
    store, run = setup(prepared)

    async def provider():
        return result(ProviderUsage(11, 1, None))

    outcome = await call(RunBudget.start(store, run), run, provider)
    assert outcome.blocked
    assert outcome.call_record["state"] == "unknown"
    assert outcome.call_record["input_tokens"] == 11
    assert outcome.run_record["status"] == "completed"
    assert any(
        a["code"] == "provider_request_limit_exceeded" for a in outcome.run_record["actions"]
    )


async def test_unrepresentable_actual_cost_is_retained_in_usage_evidence(prepared):
    maximum = 2**53 - 1
    store, run = setup(prepared, budget_micro_usd=maximum)
    p = price(run, input_micro_usd_per_million=maximum, output_micro_usd_per_million=0)

    async def provider():
        return result(ProviderUsage(maximum, 0, 0))

    outcome = await RunBudget.start(store, run).call(
        0, price=p, input_limit=1, output_limit=0, provider=provider
    )
    assert outcome.blocked
    assert outcome.call_record["state"] == "unknown"
    observed = artifact_json(store, outcome.run_record, "usage-" + outcome.call_record["call_id"])
    assert observed["calculated_micro_usd"] == (maximum * maximum + 999_999) // 1_000_000
    assert observed["usage"]["input_tokens"] == maximum


@pytest.mark.parametrize("missing", ["price", "usage", "input"])
async def test_manifest_with_missing_referenced_file_is_not_skipped(prepared, missing):
    store, run = setup(prepared)
    first = RunBudget.start(store, run)
    await call(first, run)
    current = first.record
    if missing == "input":
        target = (
            store.path_for("case", run["case_id"])
            / "inputs"
            / store.case(run["case_id"])["inputs"][0]["path"]
        )
    else:
        kind = "price" if missing == "price" else "log"
        target = store.path_for("run", run["run_id"]) / next(
            a["path"] for a in current["artifacts"] if a["kind"] == kind
        )
    second = RunBudget.start(store, new_run(run))
    target.unlink()
    attempts = []

    async def provider():
        attempts.append(1)
        return result()

    with pytest.raises(BudgetError, match="budget_history_invalid"):
        await call(second, run, provider)
    assert attempts == []


async def test_completed_settlement_supersedes_pending_reservation_without_resetting_history(
    prepared,
):
    store, run = setup(prepared)
    first = RunBudget.start(store, run)

    async def provider():
        return result(ProviderUsage(11, 1, 0))

    final = await call(first, run, provider)
    assert final.blocked
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "reserved"
    assert store.run(run["run_id"])["model_calls"][0]["state"] == "settled"
    second = RunBudget.start(store, new_run(run))
    next_result = await call(second, run)
    assert next_result.call_record["state"] == "settled"


async def test_settlement_persistence_failure_keeps_full_reservation_and_lock(prepared):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    original = store.save_pending
    saves = []

    def save(record):
        saves.append(record["model_calls"][0]["state"])
        if len(saves) == 2:
            raise OSError("settlement failed")
        original(record)

    with (
        patch.object(store, "save_pending", side_effect=save),
        pytest.raises(OSError, match="settlement failed"),
    ):
        await call(budget, run)
    assert saves == ["reserved", "settled"]
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "reserved"
    assert (store.base_path / f"locks/model/{run['case_id']}.lock").is_file()


async def test_unknown_lock_owner_is_never_taken_over(prepared):
    store, run = setup(prepared)
    budget = RunBudget.start(store, run)
    lock = OwnedLock(
        store.base_path / f"locks/model/{run['case_id']}.lock", str(uuid.uuid4())
    ).acquire()
    before = read_regular(lock.path, 4096)
    try:
        with pytest.raises(BudgetError, match="budget_history_invalid"):
            await call(budget, run)
        assert read_regular(lock.path, 4096) == before
    finally:
        lock.release()


async def test_integer_rounding_includes_explicit_extra_maximum(prepared):
    store, run = setup(prepared)
    terms = price(
        run,
        input_micro_usd_per_million=2_000_001,
        output_micro_usd_per_million=3_000_001,
        extra_max_micro_usd=7,
    )

    async def provider():
        return result(ProviderUsage(1, 1, 2))

    outcome = await RunBudget.start(store, run).call(
        0, price=terms, input_limit=2, output_limit=3, provider=provider
    )
    assert outcome.call_record["reserved_micro_usd"] == 21
    assert outcome.call_record["calculated_micro_usd"] == 8


async def test_actual_model_mismatch_cannot_be_settled_at_requested_price(prepared):
    store, run = setup(prepared)

    async def provider():
        return replace(result(), model="claude-from-the-future")

    outcome = await call(RunBudget.start(store, run), run, provider)
    assert outcome.call_record["state"] == "unknown"
    assert outcome.call_record["calculated_micro_usd"] is None
    assert outcome.call_record["reserved_micro_usd"] == 3
    observed = artifact_json(store, outcome.run_record, "usage-" + outcome.call_record["call_id"])
    assert observed["model"] == "claude-from-the-future"


async def test_stop_reservation_is_never_automatically_taken_over(prepared):
    class ProcessStopped(BaseException):
        pass

    store, run = setup(prepared, step_timeout_ms=60)

    async def stopped():
        raise ProcessStopped()

    with pytest.raises(ProcessStopped):
        await call(RunBudget.start(store, run, clock_ns=lambda: 0), run, stopped)
    lock_path = store.base_path / f"locks/model/{run['case_id']}.lock"
    original = read_regular(lock_path, 4096)
    next_budget = RunBudget.start(store, new_run(run))
    attempts = []

    async def provider():
        attempts.append(1)
        return result()

    with pytest.raises(BudgetError, match="step_timeout"):
        await call(next_budget, run, provider)
    assert attempts == []
    assert read_regular(lock_path, 4096) == original
    assert store.pending_run(run["run_id"])["model_calls"][0]["state"] == "reserved"


async def test_monotonic_total_deadline_is_not_reset_after_settled_call(prepared):
    store, run = setup(prepared, run_timeout_ms=100)
    now = [0]
    budget = RunBudget.start(store, run, clock_ns=lambda: now[0])
    await call(budget, run)
    now[0] = 101_000_000
    with pytest.raises(BudgetError, match="run_timeout"):
        await call(budget, run)
    assert len(budget.record["model_calls"]) == 1


async def test_deadline_expired_during_history_audit_does_not_create_reservation(prepared):
    store, run = setup(prepared, run_timeout_ms=100)
    now = [0]
    budget = RunBudget.start(store, run, clock_ns=lambda: now[0])
    original = store.pending_run

    def load(run_id):
        record = original(run_id)
        now[0] = 101_000_000
        return record

    with (
        patch.object(store, "pending_run", side_effect=load),
        pytest.raises(BudgetError, match="run_timeout"),
    ):
        await call(budget, run)
    assert store.pending_run(run["run_id"])["model_calls"] == []
    assert not (store.base_path / f"locks/model/{run['case_id']}.lock").exists()

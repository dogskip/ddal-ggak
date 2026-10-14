"""A completed verification cannot hide later workflow conflicts."""

from __future__ import annotations

from uuid import uuid4

from ddk.services import verified_up
from ddk.services.source_snapshot import capture_source
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_service import VerifiedChangeService
from tests.unit.test_verified_change_engine import Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario


async def test_application_conflict_blocks_workflow_without_rewriting_ready_run(
    scenario, monkeypatch
):
    store, case, baseline, candidate = scenario
    source = await VerifiedChangeEngine(store, Evaluator()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": ["R2"]},
    )
    assert source["decision"] == "ready"
    service = VerifiedChangeService(store.repository)

    async def verify(*args, **kwargs):
        return source

    monkeypatch.setattr(service, "verify", verify)
    monkeypatch.setattr(
        service,
        "apply",
        lambda **kwargs: {"state": "conflict", "actions": [{"code": "target_changed"}]},
    )
    monkeypatch.setattr(verified_up, "VerifiedChangeService", lambda _: service)
    monkeypatch.setattr(verified_up, "capture_git_source", lambda *a, **k: capture_source(baseline))
    monkeypatch.setattr(
        verified_up, "capture_git_worktree", lambda *a, **k: capture_source(candidate)
    )
    result = await verified_up.up(
        store.repository,
        case_id=case["case_id"],
        apply=True,
        quiescence_confirmed=True,
        local_storage_confirmed=True,
    )
    assert result["status"] == "blocked", result
    assert result["decision"] == "ready" and result["application"]["state"] == "conflict"
    assert {a["code"] for a in result["actions"]} >= {"target_changed"}
    assert store.run(source["run_id"]) == source

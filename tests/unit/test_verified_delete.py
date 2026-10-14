from __future__ import annotations

import copy
from uuid import uuid4

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.artifact_applier import ArtifactApplier
from ddk.services.verified_change_engine import VerifiedChangeEngine
from tests.unit.test_verified_change_engine import Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario


async def deleted_run(scenario, allowed):
    store, old, baseline, candidate = scenario
    case = copy.deepcopy(old)
    case["case_id"] = str(uuid4())
    for req in case["requirements"]:
        req["allow_delete"] = allowed
    payloads = {
        r["path"]: (store.path_for("case", old["case_id"]) / "inputs" / r["path"]).read_bytes()
        for r in case["inputs"]
    }
    store.publish_case(case, payloads)
    (candidate / "src/App.tsx").unlink()
    run = await VerifiedChangeEngine(store, Evaluator()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": [case["requirements"][0]["requirement_id"]]},
    )
    return store, case, run


@pytest.mark.parametrize("allowed", [False, True])
async def test_delete_requires_explicit_requirement_authority(scenario, allowed):
    store, case, run = await deleted_run(scenario, allowed)
    assert run["decision"] == ("ready" if allowed else "blocked")
    if allowed:
        change = run["changes"][0]
        assert change["action"] == "delete" and change["after_sha256"] is None
        assert store.run(run["run_id"]) == run


@pytest.mark.parametrize("failure", ["none", "after-delete", "external-recreate"])
async def test_delete_apply_and_recovery_preserve_external_files(scenario, monkeypatch, failure):
    store, case, run = await deleted_run(scenario, True)
    target = store.repository / "src/App.tsx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"before")
    target.chmod(0o644)
    applier = ArtifactApplier()
    original = applier.write

    def write(*args, **kwargs):
        result = original(*args, **kwargs)
        if failure == "external-recreate":
            target.write_bytes(b"external owner edit")
        if failure != "none":
            raise OSError("interrupted after deletion")
        return result

    monkeypatch.setattr(applier, "write", write)
    receipt = applier.apply_run(
        store,
        apply_id=str(uuid4()),
        case_id=case["case_id"],
        run_id=run["run_id"],
        run_sha256=record_digest(run),
        changes_sha256=record_digest(run["changes"]),
        quiescence_confirmed=True,
        local_storage_confirmed=True,
    )
    if failure == "none":
        assert receipt["state"] == "applied" and not target.exists()
    elif failure == "after-delete":
        assert receipt["state"] == "rolled_back" and target.read_bytes() == b"before"
    else:
        assert receipt["state"] == "unknown" and target.read_bytes() == b"external owner edit"

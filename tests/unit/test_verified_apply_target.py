from __future__ import annotations

import copy
import json
from dataclasses import replace
from uuid import uuid4

import pytest

from ddk.models.verified_change import record_digest
from ddk.services.artifact_applier import ArtifactApplier
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair
from tests.unit.test_verified_repair import blocked as blocked


async def test_repair_applies_against_exact_sealed_original_candidate(blocked):
    (store, case, _, _), source = blocked

    async def provider(request):
        return answer()

    result = await repair(blocked, provider)
    target = store.repository / "src/App.tsx"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"after")
    target.chmod(0o644)
    receipt = ArtifactApplier().apply_run(
        store,
        apply_id=str(uuid4()),
        case_id=case["case_id"],
        run_id=result["run_id"],
        run_sha256=record_digest(result),
        changes_sha256=record_digest(result["changes"]),
        quiescence_confirmed=True,
        local_storage_confirmed=True,
        target_run_id=source["run_id"],
    )
    assert receipt["state"] == "applied" and target.read_bytes() == b"fixed"
    assert receipt["entries"][0]["before_sha256"] == source["changes"][0]["after_sha256"]
    assert store.load_apply(receipt["apply_id"]) == receipt


def test_application_delta_includes_restored_paths_and_recomputes_actions():
    from ddk.models.verified_change import application_changes

    case = {"inputs": [{"role": "source", "path": "a", "sha256": "good", "mode": 420}]}
    source = {
        "changes": [
            {"path": "a", "after_sha256": "bad", "after_mode": 420},
            {"path": "new", "after_sha256": "draft", "after_mode": 420},
        ]
    }
    final = {"changes": [{"path": "new", "after_sha256": "fixed", "after_mode": 420}]}
    changes = {c["path"]: c for c in application_changes(case, final, source)}
    assert changes["a"] == {
        "path": "a",
        "action": "update",
        "before_sha256": "bad",
        "before_mode": 420,
        "after_sha256": "good",
        "after_mode": 420,
    }
    assert changes["new"]["action"] == "update"
    assert changes["new"]["before_sha256"] == "draft"
    reverse = application_changes(
        case,
        {"changes": []},
        {"changes": [{"path": "a", "after_sha256": None, "after_mode": None}]},
    )
    assert reverse[0]["action"] == "create"


@pytest.mark.parametrize("new_file", [False, True])
async def test_application_covers_reverted_path_and_modified_candidate_addition(scenario, new_file):
    from ddk.services.source_snapshot import capture_source
    from ddk.services.verified_budget import ProviderResult, ProviderUsage
    from ddk.services.verified_change_engine import VerifiedChangeEngine
    from ddk.services.verified_repair import RepairReply, VerifiedRepairEngine
    from tests.unit.test_verified_budget import price
    from tests.unit.test_verified_change_engine import Evaluator, fixed_file

    store, original, baseline, candidate = scenario
    case = copy.deepcopy(original)
    case["case_id"] = str(uuid4())
    case["scope_paths"].append("src/other.tsx")
    (candidate / "src/other.tsx").write_bytes(b"draft")
    (candidate / "src/other.tsx").chmod(0o644)
    if not new_file:
        (baseline / "src/other.tsx").write_bytes(b"old")
        (baseline / "src/other.tsx").chmod(0o644)
        f = fixed_file("src/other.tsx", b"old")
        case["inputs"].append({**f.manifest_entry(), "role": "source"})
    case["baseline_tree_sha256"] = capture_source(baseline).tree_sha256
    inputs = {
        i["path"]: (store.path_for("case", original["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in original["inputs"]
    }
    if not new_file:
        inputs["src/other.tsx"] = b"old"
    store.publish_case(case, inputs)

    class Observer(Evaluator):
        async def evaluate(self, request):
            content = {f.path: f.content for f in request.snapshot.files}
            self.statuses = {
                ("candidate", c["check_id"]): "failed"
                for c in request.checks
                if c["role"] == "target"
                and (
                    content["src/App.tsx"] != b"before" or content.get("src/other.tsx") != b"fixed"
                )
            }
            return replace(await super().evaluate(request), output_bytes=3)

    source = await VerifiedChangeEngine(store, Observer()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={p: ["R2"] for p in case["scope_paths"]},
    )
    assert source["decision"] == "blocked"

    async def provider(request):
        body = json.dumps(
            {
                "files": [
                    {"path": "src/App.tsx", "content": "before"},
                    {"path": "src/other.tsx", "content": "fixed"},
                ]
            }
        )
        return ProviderResult(
            RepairReply(body, False, len(body)),
            ProviderUsage(1, 1, 0),
            "anthropic",
            "claude-sonnet-5-5",
        )

    final = await VerifiedRepairEngine(store, Observer(), provider).repair(
        source["run_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        price=price(source),
        input_limit=4096,
        output_limit=4096,
    )
    assert final["decision"] == "ready", final["actions"]
    assert [c["path"] for c in final["changes"]] == ["src/other.tsx"]
    for path in ["src/App.tsx", "src/other.tsx"]:
        target = store.repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((candidate / path).read_bytes())
        target.chmod(0o644)
    receipt = ArtifactApplier().apply_run(
        store,
        apply_id=str(uuid4()),
        case_id=case["case_id"],
        run_id=final["run_id"],
        run_sha256=record_digest(final),
        changes_sha256=record_digest(final["changes"]),
        quiescence_confirmed=True,
        local_storage_confirmed=True,
        target_run_id=source["run_id"],
    )
    assert receipt["state"] == "applied"
    assert (store.repository / "src/App.tsx").read_bytes() == b"before"
    assert (store.repository / "src/other.tsx").read_bytes() == b"fixed"
    assert store.load_apply(receipt["apply_id"]) == receipt

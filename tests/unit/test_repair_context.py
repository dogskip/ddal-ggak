from __future__ import annotations

import json

from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair
from tests.unit.test_verified_repair import blocked as blocked


async def test_rounds_keep_the_exact_same_immutable_prefix_and_retain_context(blocked):
    requests = []

    async def provider(request):
        requests.append(json.loads(request.prompt))
        return answer("not-yet" if len(requests) == 1 else "fixed")

    result = await repair(blocked, provider)
    assert result["decision"] == "ready", result["actions"]
    assert requests[0]["immutable_prefix"] == requests[1]["immutable_prefix"]
    assert requests[0]["round_context"]["round_no"] == 0
    assert requests[1]["round_context"]["round_no"] == 1
    assert result["context_digests"]
    artifacts = {a["artifact_id"]: a for a in result["artifacts"]}
    for context in result["context_digests"]:
        assert artifacts[context["source_artifact_id"]]["sha256"] == context["raw_sha256"]
        assert artifacts[context["compacted_artifact_id"]]["sha256"] == context["compacted_sha256"]
    assert all(call["cache_prefix_sha256"] for call in result["model_calls"])


def test_ax_comparison_matches_the_observed_step_and_retains_nullable_lessons(scenario):
    from ddk.models.verified_change import canonical_json
    from ddk.services.source_snapshot import capture_source
    from ddk.services.verified_change_engine import EvaluationArtifact, EvaluationOutcome
    from ddk.services.verified_repair import _request
    from tests.unit.test_verified_budget import price

    _, case, _, candidate = scenario

    def ax(ident, step, name):
        return EvaluationArtifact(
            ident,
            "ax_snapshot",
            f"artifacts/{ident}.json",
            canonical_json({"step_id": step, "snapshot": f'- heading "{name}"'}),
        )

    first, second = ax("first", "first", "First"), ax("second", "second", "Second")
    current = ax("current", "second", "Second")
    baseline = EvaluationOutcome(
        results=({"check_id": "target", "artifact_ids": ["first", "second"]},),
        artifacts=(first, second),
    )
    outcome = EvaluationOutcome(
        results=(
            {
                "check_id": "target",
                "status": "failed",
                "reason_code": "failed",
                "artifact_ids": ["current"],
            },
        ),
        artifacts=(current,),
    )
    request = _request(
        case,
        capture_source(candidate),
        {"src/App.tsx"},
        outcome,
        0,
        price({"evaluator_sha256": case["evaluator_sha256"]}),
        8192,
        4096,
        ({"check_id": "target", "resolved_in_round": None, "resolved_patch_sha256": None},),
        baseline_outcome=baseline,
    )
    context = json.loads(request.prompt)["round_context"]
    assert context["failed_checks"][0]["diagnostics"][0]["content"] == ""
    assert context["previous_failures"][0]["resolved_in_round"] is None

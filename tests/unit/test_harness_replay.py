from __future__ import annotations

import copy

from ddk.models.verified_change import canonical_json
from ddk.services.verified_budget import ProviderUsage
from ddk.services.verified_replay import replay_run
from tests.unit.test_verified_change_engine import Evaluator, verify
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair
from tests.unit.test_verified_repair import blocked as blocked


async def test_replay_checks_canonical_evidence_without_reexecuting_or_changing_it(scenario):
    run = await verify(scenario, Evaluator())
    store = scenario[0]
    before = store.run_bytes(run["run_id"])
    result = replay_run(store, run["run_id"])
    assert result["evidence_integrity"] is True
    assert result["original_decision"] == result["replay_decision"] == "ready"
    assert result["execution_repeated"] is False
    assert store.run_bytes(run["run_id"]) == before


async def test_replay_blocks_hash_valid_but_arithmetically_forged_settlement(blocked):
    (store, _, _, _), _ = blocked

    async def provider(request):
        return answer()

    run = await repair(blocked, provider)
    forged = copy.deepcopy(run)
    forged["model_calls"][0]["calculated_micro_usd"] += 1
    # This changes only a bounded cost fact and keeps the JSON structurally valid.
    path = store.path_for("run", run["run_id"]) / "run.json"
    path.write_bytes(canonical_json(forged))
    result = replay_run(store, run["run_id"])
    assert result["replay_decision"] == "blocked"
    assert result["evidence_integrity"] is False
    assert result["actions"][0]["code"] == "replay_evidence_invalid"
    assert path.read_bytes() == canonical_json(forged)


async def test_nonzero_cache_usage_is_recorded_but_never_assumed_free(blocked):
    async def provider(request):
        return answer(usage=ProviderUsage(1, 1, 0, cache_read_tokens=8, cache_write_tokens=0))

    result = await repair(blocked, provider)
    assert result["decision"] == "blocked"
    assert result["model_calls"][0]["state"] == "unknown"
    assert result["model_calls"][0]["cache_read_tokens"] == 8

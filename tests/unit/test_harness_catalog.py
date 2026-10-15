from __future__ import annotations

import copy
import re
from pathlib import Path
from uuid import uuid4

import pytest

from ddk.services.source_snapshot import materialize_snapshot
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_index import VerifiedIndexCatalog
from ddk.services.workspace_lease import WorkspaceLease
from tests.unit.test_verified_change_engine import Evaluator
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair
from tests.unit.test_verified_repair import blocked as blocked


def test_catalog_has_sixteen_logical_tables_and_nullable_cache_metadata(scenario):
    catalog = VerifiedIndexCatalog(scenario[0])
    assert len(catalog.tables) == 16
    assert {"gate_verdicts", "context_digests", "stall_diagnoses", "worktree_leases"} <= set(
        catalog.tables
    )
    with catalog._connect(readonly=True) as db:
        names = {r[1] for r in db.execute("PRAGMA table_info(model_calls)")}
        assert {"cache_read_tokens", "cache_write_tokens", "cache_prefix_sha256"} <= names


def test_public_catalog_documents_every_actual_column_and_key(scenario):
    catalog = VerifiedIndexCatalog(scenario[0])
    text = (Path(__file__).parents[2] / "docs/CATALOG.md").read_text()
    sections = dict(re.findall(r"^## ([a-z_]+)\n(.*?)(?=^## |\Z)", text, re.M | re.S))
    assert set(sections) == set(catalog.tables)
    with catalog._connect(readonly=True) as db:
        for table in catalog.tables:
            actual = [
                (
                    r[1],
                    r[2] or "untyped",
                    f"primary key {r[5]}" if r[5] else "required" if r[3] else "nullable",
                )
                for r in db.execute(f"PRAGMA table_info({table})")
            ]
            documented = re.findall(
                r"^\| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \|$", sections[table], re.M
            )
            assert documented == actual, table


def test_reindex_refuses_a_new_canonical_case_before_publication(scenario, monkeypatch):
    store, case, _, _ = scenario
    catalog = VerifiedIndexCatalog(store)
    before = catalog.dump()
    other = copy.deepcopy(case)
    other["case_id"] = str(uuid4())
    inputs = {
        i["path"]: (store.path_for("case", case["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in case["inputs"]
    }
    original = catalog._case

    def concurrent_write(db, record):
        store.publish_case(other, inputs)
        original(db, record)

    monkeypatch.setattr(catalog, "_case", concurrent_write)
    with pytest.raises(ValueError, match="catalog_source_changed"):
        catalog.reindex_all()
    assert catalog.dump() == before
    assert store.case(other["case_id"]) == other


async def test_context_projection_and_latest_gate_are_rebuild_and_insert_order_invariant(blocked):
    (store, case, _, _), source = blocked

    async def provider(request):
        return answer()

    final = await repair(blocked, provider)
    catalog = VerifiedIndexCatalog(store)
    contexts = catalog.query("context_digests")
    assert contexts and all(r["run_id"] == final["run_id"] for r in contexts)
    gates = catalog.query("gate_verdicts")
    assert next(r for r in gates if r["plane"] == "all")["run_id"] == final["run_id"]
    before = catalog.dump()
    catalog.upsert_run(source)
    assert catalog.dump() == before
    catalog.reindex_all()
    assert catalog.dump() == before
    assert catalog.lessons(case["case_id"], "target")


async def test_real_workspace_receipts_project_only_after_owned_cleanup(scenario):
    class Observer(Evaluator):
        async def evaluate(self, request):
            with WorkspaceLease(
                request.input_tree_sha256, request.phase, request.round_no, request.workspace_event
            ) as folder:
                materialize_snapshot(request.snapshot, Path(folder) / "app")
                return await super().evaluate(request)

    store, case, baseline, candidate = scenario
    run = await VerifiedChangeEngine(store, Observer()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": ["R2"]},
    )
    assert run["decision"] == "ready", run["actions"]
    assert len(run["workspace_leases"]) == 2
    rows = VerifiedIndexCatalog(store).query("worktree_leases")
    assert len(rows) == 2 and all(r["state"] == "released" for r in rows)
    assert all(r["released_at"] is not None for r in rows)


async def test_mcp_ledger_exposes_new_metadata_without_private_text(blocked):
    import json

    from ddk.server import mcp

    (store, _, _, _), _ = blocked

    async def provider(request):
        return answer()

    await repair(blocked, provider)
    reply = await mcp.call_tool(
        "ddk_query_ledger", {"repository": str(store.repository), "table": "context_digests"}
    )
    text = reply[0][0].text if isinstance(reply, tuple) else reply[0].text
    rows = json.loads(text)["rows"]
    assert rows and "raw_bytes" in rows[0] and "compacted_bytes" in rows[0]
    assert "record_json" not in text and "diagnostic_summary" not in text

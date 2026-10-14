from __future__ import annotations

import sqlite3

import pytest

from ddk.services.verified_index import VerifiedIndexCatalog
from tests.unit.test_verified_change_engine import scenario as scenario


def test_catalog_rebuild_is_identical_and_hooks_follow_json(scenario):
    store, case, _, _ = scenario
    catalog = VerifiedIndexCatalog(store)
    assert catalog.query("cases")[0]["case_id"] == case["case_id"]
    original = catalog.dump()
    catalog.reindex_all()
    assert catalog.dump() == original
    with sqlite3.connect(catalog.path) as db:
        assert db.execute("pragma journal_mode").fetchone()[0] == "wal"
        tables = {r[0] for r in db.execute("select name from sqlite_master where type='table'")}
        assert set(catalog.tables) <= tables
    catalog.path.write_bytes(b"corrupt database")
    catalog.reindex_all()
    assert catalog.dump() == original


def test_index_failure_does_not_undo_published_case(tmp_path, scenario, monkeypatch):
    store, case, _, _ = scenario
    from ddk.services.verified_change_store import VerifiedChangeStore

    monkeypatch.setattr(
        VerifiedIndexCatalog,
        "upsert_case",
        lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("busy")),
    )
    other = VerifiedChangeStore(tmp_path / "other")
    inputs = {
        i["path"]: (store.path_for("case", case["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in case["inputs"]
    }
    other.publish_case(case, inputs)
    assert other.case(case["case_id"]) == case


def test_read_query_cannot_select_unknown_table(scenario):
    catalog = VerifiedIndexCatalog(scenario[0])
    with pytest.raises(ValueError):
        catalog.query("cases; DROP TABLE cases")


def test_reindex_failure_preserves_previous_catalog(scenario, monkeypatch):
    catalog = VerifiedIndexCatalog(scenario[0])
    before = catalog.dump()
    monkeypatch.setattr(
        catalog, "_case", lambda *a: (_ for _ in ()).throw(ValueError("rebuild failed"))
    )
    with pytest.raises(ValueError):
        catalog.reindex_all()
    assert catalog.dump() == before


def test_catalog_refuses_hardlinks_without_changing_external_database(scenario, tmp_path):
    import os

    catalog = VerifiedIndexCatalog(scenario[0])
    external = tmp_path / "external.sqlite3"
    with sqlite3.connect(external) as db:
        db.execute("create table protected(value)")
    external.chmod(0o644)
    original = external.read_bytes()
    catalog.path.unlink()
    os.link(external, catalog.path)
    with pytest.raises(ValueError, match="unsafe_index_path"):
        catalog.upsert_case(scenario[1])
    assert external.read_bytes() == original
    assert external.stat().st_mode & 0o777 == 0o644


def test_query_order_and_projection_survive_rebuild(scenario):
    import copy

    store, case, _, _ = scenario
    other = copy.deepcopy(case)
    other["case_id"] = "00000000-0000-4000-8000-000000000001"
    inputs = {
        i["path"]: (store.path_for("case", case["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in case["inputs"]
    }
    store.publish_case(other, inputs)
    catalog = VerifiedIndexCatalog(store)
    before = catalog.query("cases", limit=1)
    catalog.reindex_all()
    assert catalog.query("cases", limit=1) == before
    assert catalog.query("cases", columns={"case_id"}, limit=1) == [
        {"case_id": before[0]["case_id"]}
    ]


async def test_optional_catalog_lock_failure_does_not_interrupt_repair(scenario, monkeypatch):
    from contextlib import contextmanager
    from uuid import uuid4

    from ddk.services.verified_change_engine import VerifiedChangeEngine
    from tests.unit.test_verified_repair import ObservingEvaluator, answer, repair

    store, case, baseline, candidate = scenario
    source = await VerifiedChangeEngine(store, ObservingEvaluator()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": ["R2"]},
    )

    @contextmanager
    def busy(self):
        raise ValueError("catalog_busy_reindex_required")
        yield

    monkeypatch.setattr(VerifiedIndexCatalog, "_lock", busy)

    async def provider(request):
        return answer()

    final = await repair((scenario, source), provider, run_id=str(uuid4()))
    assert final["decision"] == "ready" and final["model_calls"][0]["state"] == "settled"
    assert store.run(final["run_id"]) == final


async def test_binary_deletion_rebuilds_with_complete_derived_fields(scenario):
    import copy
    from uuid import uuid4

    from ddk.services.source_snapshot import capture_source
    from ddk.services.verified_change_engine import VerifiedChangeEngine
    from tests.unit.test_verified_change_engine import Evaluator, fixed_file

    store, old, baseline, candidate = scenario
    payload = b"\x89PNG\x00\xff"
    (baseline / "logo.png").write_bytes(payload)
    (baseline / "logo.png").chmod(0o644)
    case = copy.deepcopy(old)
    case["case_id"] = str(uuid4())
    case["scope_paths"].append("logo.png")
    for r in case["requirements"]:
        r["allow_delete"] = True
    case["inputs"].append({**fixed_file("logo.png", payload).manifest_entry(), "role": "source"})
    case["baseline_tree_sha256"] = capture_source(baseline).tree_sha256
    inputs = {
        i["path"]: (store.path_for("case", old["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in old["inputs"]
    }
    store.publish_case(case, {**inputs, "logo.png": payload})
    run = await VerifiedChangeEngine(store, Evaluator()).verify(
        case["case_id"],
        baseline=baseline,
        candidate=candidate,
        run_id=str(uuid4()),
        change_requirements={"src/App.tsx": ["R2"], "logo.png": ["R2"]},
    )
    assert run["decision"] == "ready"
    catalog = VerifiedIndexCatalog(store)
    row = next(r for r in catalog.query("file_changes") if r["path"] == "logo.png")
    assert row["size_delta_bytes"] == -len(payload) and row["hunk_count"] == 1
    original = catalog.dump()
    catalog.reindex_all()
    assert catalog.dump() == original


def test_catalog_counts_separated_unified_diff_blocks(scenario, tmp_path):
    import hashlib
    import json
    import subprocess
    import sys

    from ddk.services.verified_index import _HUNKS_WORKER

    old = "\n".join(str(i) for i in range(30)).encode()
    lines = old.decode().split("\n")
    lines[3], lines[25] = "changed-three", "changed-twenty-five"
    new = "\n".join(lines).encode()
    rows = []
    for name, payload in [("before", old), ("after", new)]:
        path = tmp_path / name
        path.write_bytes(payload)
        rows.append(
            {
                "path": str(path),
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    result = subprocess.run(
        [sys.executable, "-I", "-c", _HUNKS_WORKER],
        input=json.dumps([{"path": "app.py", "before": rows[0], "after": rows[1]}]).encode(),
        capture_output=True,
        check=True,
        timeout=3,
    )
    assert json.loads(result.stdout)["app.py"] == 2

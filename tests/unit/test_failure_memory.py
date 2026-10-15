from __future__ import annotations

import copy
import json
import sqlite3
from uuid import uuid4

from ddk.services.verified_index import VerifiedIndexCatalog
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair
from tests.unit.test_verified_repair import blocked as blocked


async def test_resolved_lessons_cross_cases_and_rebuild_from_the_same_canonical_facts(blocked):
    (store, case, _, _), _ = blocked
    calls = []

    async def provider(request):
        calls.append(request)
        return answer("not-yet" if len(calls) == 1 else "fixed")

    final = await repair(blocked, provider)
    assert final["decision"] == "ready"
    catalog = VerifiedIndexCatalog(store)
    check_id = next(c["check_id"] for c in case["checks"] if c["role"] == "target")
    rows = [r for r in catalog.query("failure_lessons") if r["check_id"] == check_id]
    assert rows and all(r["resolved_in_round"] == 2 for r in rows)
    assert all(r["resolved_patch_sha256"] == final["rounds"][-1]["changes_sha256"] for r in rows)
    other = copy.deepcopy(case)
    other["case_id"] = str(uuid4())
    payloads = {
        i["path"]: (store.path_for("case", case["case_id"]) / "inputs" / i["path"]).read_bytes()
        for i in case["inputs"]
    }
    store.publish_case(other, payloads)
    lessons = catalog.lessons(other["case_id"], check_id, "check_failed")
    assert lessons and all(r["case_id"] == case["case_id"] for r in lessons)
    assert all(r["resolved_in_round"] is not None for r in lessons)
    before = catalog.dump()
    catalog.reindex_all()
    assert catalog.dump() == before


async def test_sqlite_diagnostic_tampering_never_enters_repair_context(blocked):
    (store, case, _, _), _ = blocked

    async def provider(request):
        return answer()

    final = await repair(blocked, provider)
    assert final["decision"] == "ready"
    catalog = VerifiedIndexCatalog(store)
    with sqlite3.connect(catalog.path) as db:
        db.execute("UPDATE failure_lessons SET diagnostic_summary='forged source text'")
    check_id = next(c["check_id"] for c in case["checks"] if c["role"] == "target")
    lessons = catalog.lessons(case["case_id"], check_id)
    assert "forged source text" not in json.dumps(lessons)
    assert lessons and all(r["resolved_in_round"] is not None for r in lessons)

from __future__ import annotations

import tomllib

import pytest

from ddk.services.case_bootstrapper import CaseBootstrapper
from tests.e2e.test_verified_browser import sites as sites
from tests.e2e.test_verified_browser import unhandled_async_errors as unhandled_async_errors

pytestmark = [pytest.mark.playwright, pytest.mark.usefixtures("unhandled_async_errors")]


async def test_discovery_observes_headless_evidence_without_approving_it(tmp_path, sites):
    result = await CaseBootstrapper(tmp_path).discover(sites[0], viewport=(640, 480))
    assert result["status"] == "draft"
    assert result["observation"]["cleanup_complete"]
    assert {"screenshot", "ax_snapshot", "dom", "data"} <= {
        a["kind"] for a in result["observation"]["artifacts"]
    }
    config = tomllib.loads((tmp_path / ".ddk/verify.draft.toml").read_text())
    assert config["draft"] is True
    check = next(c for c in config["checks"] if c["kind"] == "browser")
    assert check["role"] == "preserve"
    assert any(s["action"] == "expect-no-console-error" for s in check["steps"])
    blocked = await CaseBootstrapper(tmp_path).initialize("Fix behavior", dry_run=True)
    assert blocked["actions"][0]["code"] == "draft_criteria_unapproved"
    assert not (tmp_path / ".ddk/verified-change").exists()


async def test_discovery_approval_up_gate_replay_and_rebuild_use_real_browser(tmp_path):
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_evidence import read_evidence
    from ddk.services.verified_gate import gate_status
    from ddk.services.verified_index import VerifiedIndexCatalog
    from ddk.services.verified_replay import replay_run
    from ddk.services.verified_up import up
    from tests.unit.test_case_bootstrapper import setup_repo
    from tests.unit.test_case_discovery import valid_draft

    setup_repo(tmp_path)
    boot = CaseBootstrapper(tmp_path)
    discovery = await boot.discover(dry_run=True)
    assert discovery["draft"] and not (tmp_path / ".ddk").exists()
    await boot.discover()
    (tmp_path / ".ddk/verify.draft.toml").write_text(valid_draft())
    assert boot.approve_draft()["status"] == "approved"
    (tmp_path / "index.html").write_text('<link rel="icon" href="data:,"><h1>After</h1>')
    answer = await up(tmp_path, "Fix heading", trusted_local_approved=True)
    assert answer["status"] == "ready", answer
    store = VerifiedChangeStore(tmp_path, create=False)
    run = store.status(answer["run_id"])
    assert len(run["workspace_leases"]) == 2
    assert all(r["state"] == "released" for r in run["workspace_leases"])
    assert gate_status(tmp_path)["gate_status"] == "passed"
    assert replay_run(store, run["run_id"])["evidence_integrity"]
    diagnostic = next(a for a in run["artifacts"] if a["kind"] == "ax_snapshot")
    assert (
        read_evidence(store, run["run_id"], diagnostic["artifact_id"])["raw_sha256"]
        == diagnostic["sha256"]
    )
    catalog = VerifiedIndexCatalog(store)
    before = catalog.dump()
    catalog.reindex_all()
    assert catalog.dump() == before
    (tmp_path / "index.html").write_text("<h1>Changed after verification</h1>")
    assert gate_status(tmp_path)["gate_status"] == "reopened"
    assert store.status(run["run_id"]) == run


async def test_playwright_step_timeout_is_a_failed_check_with_owned_cleanup(
    tmp_path, sites, monkeypatch
):
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError

    from ddk.adapters import verified_browser
    from tests.e2e.test_verified_browser import settings
    from tests.unit.adapters.test_verified_browser import FIXTURE, criteria, step

    observed = []

    async def expires(*args, **kwargs):
        observed.append(True)
        raise PlaywrightTimeoutError("Locator.click: missing approved link")

    monkeypatch.setattr(verified_browser, "_step", expires)
    payload, check = criteria([step("expect-url", value="/")])
    result = await verified_browser.run_flow(
        payload,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path / "timeout",
        fixture_sha256=FIXTURE,
        references={},
        settings=await settings.__wrapped__(),
    )
    assert observed
    assert result.result["status"] == "failed"
    assert result.result["reason_code"] == "timeout"
    assert result.cleanup_complete
    assert any(a["kind"] == "ax_snapshot" for a in result.artifacts)

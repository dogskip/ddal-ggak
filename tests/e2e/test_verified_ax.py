from __future__ import annotations

import json

import pytest

from ddk.adapters.verified_browser import run_flow
from tests.e2e.test_verified_browser import settings as settings
from tests.e2e.test_verified_browser import sites as sites
from tests.unit.adapters.test_verified_browser import FIXTURE, criteria, step

pytestmark = pytest.mark.playwright


async def test_ax_assertion_retains_real_accessibility_tree(tmp_path, settings, sites):
    definition, check = criteria(
        [step("expect-ax-tree", value='- button "Add"'), step("expect-no-console-error")]
    )
    result = await run_flow(
        definition,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert result.result["status"] == "passed"
    ax = [a for a in result.artifacts if a["kind"] == "ax_snapshot"]
    assert ax and 'button "Add"' in json.loads((tmp_path / ax[0]["path"]).read_bytes())["snapshot"]
    assert result.cleanup_complete


async def test_failed_ax_assertion_still_retains_tree(tmp_path, settings, sites):
    definition, check = criteria(
        [step("expect-ax-tree", value='- button "Does not exist"', timeout_ms=100)]
    )
    result = await run_flow(
        definition,
        check=check,
        base_url=sites[0],
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=settings,
    )
    assert result.result["status"] == "failed"
    assert any(a["kind"] == "ax_snapshot" for a in result.artifacts)

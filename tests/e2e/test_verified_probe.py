from __future__ import annotations

import json

import pytest

from ddk.adapters.verified_probe import capture_probe
from tests.e2e.test_verified_browser import sites as sites

pytestmark = pytest.mark.playwright


async def test_probe_captures_png_ax_dom_and_cleanup_receipt(tmp_path, sites):
    result = await capture_probe(sites[0], tmp_path, viewport=(640, 480), selector="button")
    assert result["status"] == "ready", result
    assert result["cleanup_complete"]
    assert result["bounding_box"]["width"] > 0
    kinds = {r["kind"] for r in result["artifacts"]}
    assert {"screenshot", "ax_snapshot", "dom", "data"} <= kinds
    assert (tmp_path / "probe.png").read_bytes().startswith(b"\x89PNG")
    assert 'button "Add"' in json.loads((tmp_path / "probe.ax.json").read_bytes())["snapshot"]


async def test_probe_reference_creates_new_case_and_preserves_crop_and_original(tmp_path, sites):
    from ddk.adapters.verified_probe import register_reference
    from ddk.services.case_bootstrapper import CaseBootstrapper
    from ddk.services.verified_change_store import VerifiedChangeStore
    from tests.unit.test_case_bootstrapper import setup_repo

    output = tmp_path / "capture"
    result = await capture_probe(
        sites[0], output, viewport=(640, 480), selector="button", repository=tmp_path
    )
    setup_repo(tmp_path)
    config = {
        "scope_paths": ["index.html"],
        "checks": [
            {
                "check_id": "target",
                "role": "target",
                "viewport": {"width": 640, "height": 480},
                "steps": [{"action": "expect-visible", "selector": "body"}],
            },
            {
                "check_id": "preserve",
                "role": "preserve",
                "steps": [{"action": "expect-visible", "selector": "body"}],
            },
        ],
    }
    original = await CaseBootstrapper(tmp_path).initialize(
        "Keep button accessible",
        configuration=config,
        observed_environment=(result["environment"], None),
    )
    store = VerifiedChangeStore(tmp_path)
    renewed = register_reference(
        store, original["case_id"], result, output, "references/button.png", check_id="target"
    )
    assert (
        renewed["case_id"] != original["case_id"]
        and renewed["supersedes_case_id"] == original["case_id"]
    )
    assert store.case(original["case_id"]) == original
    flow = json.loads(
        (store.path_for("case", renewed["case_id"]) / "inputs/criteria/target.json").read_bytes()
    )
    assert flow["steps"][-1]["selector"]["value"] == "button"
    assert any(i["role"] == "reference" for i in renewed["inputs"])

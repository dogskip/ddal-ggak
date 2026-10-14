"""`ddk demo` for real: install, build, type check, lint, preview, Chromium, SSIM.

Opt-in (needs Node, network for `npm ci`, and a Chromium build):

    DDK_E2E=1 pytest tests/e2e -m playwright        # DDK_CHROMIUM_PATH=... if not installed
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ddk.demo.runner import check_prerequisites, run_demo

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.skipif(not os.environ.get("DDK_E2E"), reason="set DDK_E2E=1 to run"),
]


async def test_demo_repairs_the_first_draft_and_ends_ready(tmp_path: Path) -> None:
    assert check_prerequisites() == []
    from ddk.demo.runner import real_services

    result = await run_demo(
        tmp_path / "demo", services=real_services(os.environ.get("DDK_CHROMIUM_PATH") or None)
    )

    first = result.first_attempt
    final = result.final_state["visual_regression_report"]
    assert first is not None and first.ssim < 0.92 and first.mismatch_ratio > 0.03
    assert first.screenshot.is_file() and first.diff.is_file()
    assert final.pass_result and final.ssim_score > 0.99
    assert result.summary["fix_attempts"] == 1
    assert result.summary["release_decision"] == "ready", result.summary
    generated = result.case_path / "artifacts" / "generated" / "src" / "App.tsx"
    assert "export default function App" in generated.read_text()
    assert result.report_path is not None and result.report_path.is_file()
    assert "ready" in result.report_path.read_text(encoding="utf-8")

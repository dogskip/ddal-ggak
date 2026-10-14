"""`ddk demo` for real: install, build, type check, lint, preview, Chromium, SSIM.

Opt-in (needs Node, network for `npm ci`, and a Chromium build):

    DDK_E2E=1 pytest tests/e2e -m playwright        # DDK_CHROMIUM_PATH=... if not installed
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

from ddk.demo.runner import _npm_ci, check_prerequisites, run_demo

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.skipif(not os.environ.get("DDK_E2E"), reason="set DDK_E2E=1 to run"),
]


async def test_demo_repairs_the_first_draft_and_ends_ready(tmp_path: Path) -> None:
    assert check_prerequisites() == []
    from ddk.demo.runner import real_services

    original_dependencies: dict[str, tuple[int, str]] = {}

    async def install(project: Path) -> None:
        await _npm_ci(project)
        original_dependencies.update(_dependency_manifest(project / "node_modules"))

    result = await run_demo(
        tmp_path / "demo",
        services=real_services(os.environ.get("DDK_CHROMIUM_PATH") or None),
        install=install,
    )

    assert original_dependencies
    final_dependencies = _dependency_manifest(result.project_path / "node_modules")
    preservation = {
        "before_sha256": _manifest_sha256(original_dependencies),
        "after_sha256": _manifest_sha256(final_dependencies),
        "entry_count": len(original_dependencies),
        "unchanged": final_dependencies == original_dependencies,
    }
    (tmp_path / "dependency-preservation.json").write_text(
        json.dumps(preservation, indent=2), encoding="utf-8"
    )
    assert preservation["unchanged"]

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


def _dependency_manifest(folder: Path) -> dict[str, tuple[int, str]]:
    manifest: dict[str, tuple[int, str]] = {}
    for path in folder.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            value = "symlink:" + os.readlink(path)
        elif stat.S_ISREG(mode):
            value = hashlib.sha256(path.read_bytes()).hexdigest()
        elif stat.S_ISDIR(mode):
            value = "directory"
        else:
            continue
        manifest[path.relative_to(folder).as_posix()] = (mode, value)
    return manifest


def _manifest_sha256(manifest: dict[str, tuple[int, str]]) -> str:
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()

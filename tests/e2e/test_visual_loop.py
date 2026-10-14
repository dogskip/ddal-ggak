"""The whole delivery loop on a real Vite project: a page that looks wrong is repaired until it
matches the design, then certified.

Real: sandbox copy, `npm run build` (tsc + vite), `vite preview`, headless Chromium, SSIM.
Scripted: the model, so the run is deterministic and costs nothing.

Opt-in because it needs Node, a Chromium build and installed dependencies:

    DDK_E2E=1 pytest tests/e2e -m playwright        # DDK_CHROMIUM_PATH=... if not installed
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from ddk.adapters.chromium_browser import ChromiumBrowserAdapter
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.input import CaseInput
from ddk.services.case_artifact_store import CaseArtifactStore
from ddk.services.pipeline_runner import PipelineRunner, RuntimeServices
from ddk.services.runtime_validator import RuntimeValidator
from ddk.workspace.manager import WorkspaceManager

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.skipif(not os.environ.get("DDK_E2E"), reason="set DDK_E2E=1 to run"),
]

# The page the design shows: dark header, three cards side by side.
_GOOD = """\
const card = (title: string, value: string, accent: string) => (
  <div key={title} style={{ flex: 1, background: '#fff', borderRadius: 12, padding: 24,
    borderTop: `6px solid ${accent}` }}>
    <div style={{ color: '#64748b', fontSize: 14 }}>{title}</div>
    <div style={{ color: '#0f172a', fontSize: 36, fontWeight: 700, marginTop: 8 }}>{value}</div>
  </div>
)

export default function App() {
  return (
    <div style={{ minHeight: '100vh', background: '#f1f5f9', fontFamily: 'sans-serif' }}>
      <header style={{ background: '#0f172a', color: '#fff', padding: '20px 32px', fontSize: 22 }}>
        Sales overview
      </header>
      <main style={{ display: 'flex', gap: 24, padding: 32 }}>
        {card('Revenue', '$48,200', '#2563eb')}
        {card('Orders', '1,284', '#16a34a')}
        {card('Refunds', '37', '#dc2626')}
      </main>
    </div>
  )
}
"""

# What the "model" first produces: same content, but wrong colours and a stacked layout.
_BAD = (
    _GOOD.replace("background: '#f1f5f9'", "background: '#ffffff'")
    .replace("background: '#0f172a', color: '#fff'", "background: '#e2e8f0', color: '#0f172a'")
    .replace("display: 'flex', gap: 24, padding: 32", "display: 'block', padding: 8")
    .replace("flex: 1, background: '#fff'", "background: '#fff', marginBottom: 12")
)

_INTENT = {
    "layout_regions": [],
    "components": [],
    "interactions": [],
    "unresolved_items": [],
    "confidence": 0.9,
}
_DESIGN_SYSTEM = {"inferred_tokens": [], "primitive_components": [], "token_source": "llm"}
_PLAN = {
    "nodes": [
        {
            "id": "node-app",
            "node_type": "component",
            "target_path": "src/App.tsx",
            "dependencies": [],
            "validation_hooks": [],
            "repair_hooks": [],
        }
    ],
    "execution_order": ["node-app"],
    "target_files": ["src/App.tsx"],
    "validation_hooks": [],
    "estimated_node_count": 1,
}
_NO_PATCHES = {"convention_fixes": [], "unresolved_drift": [], "patched_files": {}}


class ScriptedModel:
    """Answers every stage by the first word of its system prompt."""

    def __init__(self) -> None:
        self.stages: list[str] = []
        self.images_in_repair: list[int] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        stage = messages[0].content.split()[0].lower()
        self.stages.append(stage)
        answers: dict[str, str] = {
            "you": json.dumps(_INTENT),
            "analyze": json.dumps(_DESIGN_SYSTEM),
            "senior": json.dumps(_PLAN),
            "generate": f"=== FILE: src/App.tsx ===\n{_BAD}",
            "normalize": json.dumps(_NO_PATCHES),
        }
        if stage == "autofix":
            self.images_in_repair.append(len(messages[-1].images or []))
            return LLMResponse(content=_GOOD, model=config.model)
        return LLMResponse(content=answers[stage], model=config.model)

    async def complete_structured(
        self, messages: list[Message], config: LLMCallConfig, output_schema: type
    ) -> LLMResponse:
        return await self.complete(messages, config)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(installed_template: Path, tmp_path: Path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(installed_template, target, symlinks=True)
    _git(target, "init", "-q")
    _git(target, "config", "user.email", "e2e@example.com")
    _git(target, "config", "user.name", "e2e")
    _git(target, "add", "-A")
    _git(target, "commit", "-q", "-m", "initial")
    return target


def _browser() -> ChromiumBrowserAdapter:
    return ChromiumBrowserAdapter(executable_path=os.environ.get("DDK_CHROMIUM_PATH"))


async def _render_design(repo: Path, out_dir: Path) -> Path:
    """Screenshot of the page as the design wants it, taken by the same browser."""
    out_dir.mkdir(parents=True)
    placeholder = out_dir / "placeholder.png"
    Image.new("RGB", (1280, 800), (255, 255, 255)).save(placeholder)
    browser = _browser()
    validator = RuntimeValidator(
        TempDirSandbox(),
        SubprocessBuildRunner(),
        browser,
        LocalScreenshotDiffAdapter(),
        preview=SubprocessPreviewLauncher(),
        visual_dir=out_dir,
    )
    good = GeneratedArtifactSet(
        case_id="design",
        files=[GeneratedFile(path="src/App.tsx", content=_GOOD, source_node_id="n", is_new=False)],
    )
    state: dict[str, Any] = {
        "case_id": "design",
        "generated_artifacts": good,
        "case_input": SimpleNamespace(
            repo_path=repo, image_paths=[placeholder], visual_reference_paths=[], visual_check=True
        ),
    }
    try:
        await validator.run(state)
    finally:
        await browser.close()
    return out_dir / "generated.png"


async def test_wrong_looking_page_is_repaired_from_the_design_and_certified(
    repo: Path, tmp_path: Path
) -> None:
    design = await _render_design(repo, tmp_path / "design")
    assert design.is_file(), "the design page could not be rendered"

    model = ScriptedModel()
    browser = _browser()
    services = RuntimeServices(
        llm=model,
        filesystem=FilesystemAdapter(),
        git=LocalGitAdapter(),
        sandbox=TempDirSandbox(),
        build_runner=SubprocessBuildRunner(),
        browser=browser,
        screenshot_diff=LocalScreenshotDiffAdapter(),
        preview=SubprocessPreviewLauncher(),
        max_fix_attempts=3,
    )
    manager = WorkspaceManager(repo)
    manager.init()
    case_path = manager.init_case("C-001")
    case_input = CaseInput(
        case_id="C-001",
        image_paths=[design],
        prompt="Build the sales overview dashboard",
        repo_path=repo,
        visual_check=True,
    )

    final = await PipelineRunner(services).run_case(case_input, case_dir=case_path)
    CaseArtifactStore(case_path).persist(case_input, final)
    status = CaseArtifactStore(case_path).load_status()

    attempts = final["fix_attempts"]
    visual = final["visual_regression_report"]
    assert len(attempts) == 1, "one repair should be enough"
    assert model.images_in_repair == [3], "reference, current page and difference image"
    assert visual.pass_result and visual.ssim_score > 0.99
    assert final["generated_artifacts"].file_map["src/App.tsx"] == _GOOD
    assert browser.blocked_requests == []
    assert status["release_decision"] == "ready", status

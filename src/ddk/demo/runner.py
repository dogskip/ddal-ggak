"""Run the demo: the bundled project, the recorded model and the real loop around them.

Everything but the model is real: dependency install, build, type check, lint, a served
preview, headless Chromium and the screenshot comparison.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from ddk.adapters.chromium_browser import ChromiumBrowserAdapter
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.demo.script import demo_model
from ddk.demo.wireframe import render_design
from ddk.i18n import t
from ddk.models.input import CaseInput
from ddk.models.visual import VisualRegressionReport
from ddk.preflight.doctor import PreflightDoctor
from ddk.services.case_artifact_store import CaseArtifactStore
from ddk.services.case_report import ReportUnavailableError, write_report
from ddk.services.pipeline_runner import PipelineRunner, RuntimeServices, StageCallback
from ddk.workspace.manager import WorkspaceManager

_CASE_ID = "C-001"
_PROMPT = "Build the dashboard shown in the design"
_INSTALL = ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
_INSTALL_TIMEOUT_S = 600


class DemoUnavailableError(RuntimeError):
    """The demo cannot run here (missing tool, folder in the way, failed install)."""


@dataclass(frozen=True)
class FirstAttempt:
    """How far the first generated page was from the design, with its screenshots kept."""

    ssim: float
    mismatch_ratio: float
    screenshot: Path
    diff: Path


@dataclass(frozen=True)
class DemoResult:
    project_path: Path
    design_path: Path
    case_path: Path
    summary: dict[str, Any]
    final_state: dict[str, Any]
    first_attempt: FirstAttempt | None
    report_path: Path | None = None


def bundled_project() -> Path:
    """The Vite + React + TypeScript project shipped with the package."""
    return Path(str(resources.files("ddk").joinpath("assets", "demo", "vite-app")))


def check_prerequisites(install_browser: Callable[[], bool] | None = None) -> list[str]:
    """What is missing on this machine, as readable lines; empty when the demo can run.

    ``install_browser`` is offered a missing Chromium once; it returns whether it got one.
    """
    problems: list[str] = []
    if shutil.which("node") is None or shutil.which("npm") is None:
        problems.append(t("Node.js 와 npm 이 필요합니다 (https://nodejs.org)."))
    browser = PreflightDoctor().check_browser()
    if browser["status"] != "pass" and install_browser is not None and install_browser():
        browser = PreflightDoctor().check_browser()
    if browser["status"] != "pass":
        problems.append(
            t("헤드리스 Chromium 을 사용할 수 없습니다: {detail}", detail=browser["detail"])
        )
    return problems


def real_services(chromium_path: str | None = None) -> RuntimeServices:
    """Real tools around the recorded model."""
    return RuntimeServices(
        llm=demo_model(),
        filesystem=FilesystemAdapter(),
        git=LocalGitAdapter(),
        sandbox=TempDirSandbox(),
        build_runner=SubprocessBuildRunner(),
        browser=ChromiumBrowserAdapter(executable_path=chromium_path),
        screenshot_diff=LocalScreenshotDiffAdapter(),
        preview=SubprocessPreviewLauncher(),
        install_dependencies=True,
        max_fix_attempts=3,
    )


async def run_demo(
    workdir: Path,
    *,
    services: RuntimeServices | None = None,
    install: Callable[[Path], Awaitable[None]] | None = None,
    on_update: StageCallback | None = None,
) -> DemoResult:
    """Copy the bundled project into ``workdir`` and run the whole loop on it."""
    project = workdir / "project"
    if project.exists():
        raise DemoUnavailableError(f"{project} already exists; pick another --workdir")
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundled_project(), project)
    await (install or _npm_ci)(project)

    design = render_design(workdir / "design.png")
    manager = WorkspaceManager(project)
    manager.init()
    case_path = manager.init_case(_CASE_ID)
    case_input = CaseInput(
        case_id=_CASE_ID,
        image_paths=[design],
        prompt=_PROMPT,
        repo_path=project,
        visual_check=True,
    )

    first: list[FirstAttempt] = []

    def watch(stage: str, update: dict[str, Any]) -> None:
        if on_update is not None:
            on_update(stage, update)
        visual = update.get("visual_regression_report")
        if stage == "validate" and not first and visual is not None and not visual.pass_result:
            first.append(_keep_first_attempt(visual, workdir / "first-attempt"))

    final_state = await PipelineRunner(services or real_services()).run_case(
        case_input, case_dir=case_path, on_update=watch
    )
    store = CaseArtifactStore(case_path)
    store.persist(case_input, final_state)
    try:
        report_path = write_report(case_path)
    except (ReportUnavailableError, OSError):
        report_path = None
    return DemoResult(
        project_path=project,
        design_path=design,
        case_path=case_path,
        summary=store.load_status(),
        final_state=final_state,
        first_attempt=first[0] if first else None,
        report_path=report_path,
    )


async def _npm_ci(project: Path) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            *_INSTALL,
            cwd=project,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=_INSTALL_TIMEOUT_S)
    except (OSError, TimeoutError) as exc:
        raise DemoUnavailableError(f"npm ci could not run: {exc}") from exc
    if process.returncode != 0:
        tail = stderr.decode(errors="replace").strip()[-400:]
        raise DemoUnavailableError(f"npm ci failed: {tail}")


def _keep_first_attempt(visual: VisualRegressionReport, folder: Path) -> FirstAttempt:
    folder.mkdir(parents=True, exist_ok=True)
    screenshot = folder / "page.png"
    diff = folder / "difference.png"
    shutil.copy(visual.generated_path, screenshot)
    if visual.diff_image_path:
        shutil.copy(visual.diff_image_path, diff)
    return FirstAttempt(
        ssim=visual.ssim_score,
        mismatch_ratio=visual.mismatch_area_ratio,
        screenshot=screenshot,
        diff=diff,
    )

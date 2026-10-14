"""run_demo drives the real graph with the recorded model; browser and tools are doubles here."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.playwright_browser import ConsoleEntry, FailedRequestEntry
from ddk.adapters.sandbox.base import CommandResult
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.demo.runner import (
    DemoUnavailableError,
    bundled_project,
    check_prerequisites,
    run_demo,
)
from ddk.demo.script import demo_model
from ddk.demo.wireframe import first_draft_boxes, reference_boxes, render_boxes
from ddk.services.pipeline_runner import RuntimeServices
from tests.fakes import FakeBuildRunner, FakePreviewLauncher


class SequenceBrowser:
    """Shows the first-draft page on the first visit and the design on later visits."""

    is_null = False

    def __init__(self, scratch: Path) -> None:
        self._scratch = scratch
        self.shots = 0

    async def capture_screenshot(
        self, url: str, output_path: Path, viewport: tuple[int, int] = (1280, 800)
    ) -> Path:
        boxes = first_draft_boxes() if self.shots == 0 else reference_boxes()
        self.shots += 1
        shutil.copy(render_boxes(boxes, self._scratch / f"shot-{self.shots}.png"), output_path)
        return output_path

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]:
        return []

    async def get_failed_requests(
        self, url: str, wait_ms: int = 5000, correlation_id: str | None = None
    ) -> list[FailedRequestEntry]:
        return []

    async def close(self) -> None:
        return None


class _InstallingBuildRunner(FakeBuildRunner):
    async def run(self, command: list[str], cwd: Path, timeout: int = 300) -> CommandResult:
        if command[:2] == ["npm", "ci"]:
            await _no_install(cwd)
        return await super().run(command, cwd, timeout)


def _services(scratch: Path) -> RuntimeServices:
    return RuntimeServices(
        llm=demo_model(),
        filesystem=FilesystemAdapter(),
        git=LocalGitAdapter(),
        sandbox=TempDirSandbox(),
        build_runner=_InstallingBuildRunner(),
        browser=SequenceBrowser(scratch),
        screenshot_diff=LocalScreenshotDiffAdapter(),
        preview=FakePreviewLauncher(),
        install_dependencies=True,
        max_fix_attempts=3,
    )


async def _no_install(project: Path) -> None:
    """Leaves what `npm ci` would, as far as the validator looks: the `vite` executable."""
    binaries = project / "node_modules" / ".bin"
    binaries.mkdir(parents=True, exist_ok=True)
    (binaries / "vite").write_text("")


def test_bundled_project_is_a_vite_app_with_a_lockfile() -> None:
    project = bundled_project()

    assert (project / "package.json").is_file()
    assert (project / "package-lock.json").is_file()
    assert (project / "src" / "App.tsx").is_file()
    assert not (project / "node_modules").exists()


async def test_demo_repairs_the_first_draft_and_certifies(tmp_path: Path) -> None:
    stages: list[str] = []

    result = await run_demo(
        tmp_path / "demo",
        services=_services(tmp_path),
        install=_no_install,
        on_update=lambda stage, update: stages.append(stage),
    )

    assert stages == [
        "intake",
        "repo_scan",
        "intent_extract",
        "design_system",
        "plan",
        "generate",
        "normalize",
        "validate",
        "autofix",
        "validate",
        "certify",
    ]
    assert result.summary["fix_attempts"] == 1
    assert result.summary["release_decision"] == "ready"
    assert result.design_path.is_file()
    assert (result.project_path / "src" / "App.tsx").is_file()
    assert result.case_path.is_dir()


async def test_first_attempt_is_kept_for_a_before_and_after(tmp_path: Path) -> None:
    result = await run_demo(tmp_path / "demo", services=_services(tmp_path), install=_no_install)

    first = result.first_attempt
    assert first is not None
    assert 0.5 < first.ssim < 0.92
    assert first.mismatch_ratio > 0.03
    assert first.screenshot.is_file() and first.diff.is_file()
    assert result.final_state["visual_regression_report"].ssim_score > 0.99


async def test_install_runs_inside_the_copied_project(tmp_path: Path) -> None:
    seen: list[Path] = []

    async def install(project: Path) -> None:
        seen.append(project)

    result = await run_demo(tmp_path / "demo", services=_services(tmp_path), install=install)

    assert seen == [result.project_path]


async def test_existing_workdir_is_not_overwritten(tmp_path: Path) -> None:
    workdir = tmp_path / "demo"
    (workdir / "project").mkdir(parents=True)

    with pytest.raises(DemoUnavailableError, match="already exists"):
        await run_demo(workdir, services=_services(tmp_path), install=_no_install)


def test_missing_node_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ddk.demo.runner.shutil.which", lambda name: None)

    problems = check_prerequisites()

    assert any("Node.js" in problem for problem in problems)


def test_all_prerequisites_present(monkeypatch: pytest.MonkeyPatch) -> None:
    class Ready:
        def check_browser(self) -> dict[str, Any]:
            return {"status": "pass", "detail": "/x/chrome"}

    monkeypatch.setattr("ddk.demo.runner.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("ddk.demo.runner.PreflightDoctor", Ready)

    assert check_prerequisites() == []


class _Browser:
    """Reports the browser as missing until ``install_browser`` has run."""

    installed = False

    def check_browser(self) -> dict[str, Any]:
        if _Browser.installed:
            return {"status": "pass", "detail": "/x/chrome"}
        return {"status": "warn", "detail": "No Chromium found"}


@pytest.fixture
def missing_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    _Browser.installed = False
    monkeypatch.setattr("ddk.demo.runner.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("ddk.demo.runner.PreflightDoctor", _Browser)


@pytest.mark.usefixtures("missing_browser")
class TestBrowserOffer:
    def test_without_an_offer_a_missing_browser_is_a_problem(self) -> None:
        problems = check_prerequisites()

        assert len(problems) == 1 and "No Chromium found" in problems[0]

    def test_a_download_the_caller_makes_removes_the_problem(self) -> None:
        def download() -> bool:
            _Browser.installed = True
            return True

        assert check_prerequisites(install_browser=download) == []

    def test_a_download_that_fails_leaves_the_problem(self) -> None:
        assert len(check_prerequisites(install_browser=lambda: False)) == 1

    def test_a_working_browser_is_never_offered_a_download(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _Browser.installed = True
        offered: list[str] = []

        def download() -> bool:
            offered.append("asked")
            return True

        assert check_prerequisites(install_browser=download) == []
        assert offered == []


async def test_demo_leaves_an_evidence_report_with_both_checks(tmp_path: Path) -> None:
    result = await run_demo(tmp_path / "demo", services=_services(tmp_path), install=_no_install)

    assert result.report_path == result.case_path / "reports" / "report.html"
    page = result.report_path.read_text(encoding="utf-8")
    assert page.count("<h3>") >= 2 and "R-10" in page
    assert page.count('src="data:image/png') >= 5  # design, 2 results, 2 differences (+ overlay)


@pytest.mark.parametrize("available", [True, False])
async def test_prerequisites_probe_the_browser_from_an_active_event_loop(
    monkeypatch: pytest.MonkeyPatch, available: bool
) -> None:
    import asyncio

    from ddk.adapters.chromium_browser import BrowserUnavailableError, ChromiumBrowserAdapter

    caller_loop = asyncio.get_running_loop()
    observed: list[asyncio.AbstractEventLoop] = []

    async def probe(self: ChromiumBrowserAdapter) -> str:
        observed.append(asyncio.get_running_loop())
        await asyncio.sleep(0)
        if not available:
            raise BrowserUnavailableError("probe actually failed")
        return "Playwright's Chromium"

    monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
    monkeypatch.setattr("ddk.demo.runner.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(ChromiumBrowserAdapter, "probe", probe)

    problems = check_prerequisites()

    assert len(observed) == 1
    assert observed[0] is not caller_loop
    assert problems == [] if available else "probe actually failed" in problems[0]


def test_real_services_install_dependencies_in_the_validation_copy() -> None:
    from ddk.demo.runner import real_services

    assert real_services().install_dependencies is True


async def test_validation_installs_dependencies_in_each_disposable_copy(tmp_path: Path) -> None:
    services = _services(tmp_path)
    result = await run_demo(tmp_path / "demo", services=services, install=_no_install)
    assert isinstance(services.build_runner, _InstallingBuildRunner)
    installs = [
        entry for entry in services.build_runner.run_log if entry["command"][:2] == ["npm", "ci"]
    ]

    assert len(installs) == 2
    assert all(Path(str(entry["cwd"])) != result.project_path for entry in installs)
    assert all(not Path(str(entry["cwd"])).exists() for entry in installs)
    assert (result.project_path / "node_modules/.bin/vite").is_file()

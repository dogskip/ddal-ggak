"""RuntimeValidator renders the built app in the sandbox and compares it with the design."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from ddk.adapters.playwright_browser import ConsoleEntry, FailedRequestEntry
from ddk.adapters.sandbox.base import CommandResult
from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.models.visual import VisualRegressionReport
from ddk.services.runtime_validator import RuntimeValidator
from tests.fakes import (
    FakePreviewLauncher,
    PaintingBrowser,
    ProjectSandbox,
    ScriptedBuildRunner,
)

BUILD = "npm run build"


def _project(*, framework: str = "vite", installed_bin: bool = True) -> dict[str, str]:
    files = {
        "package.json": json.dumps(
            {
                "name": "app",
                "scripts": {"build": "vite build"},
                "devDependencies": {framework: "^1"},
            }
        ),
        "package-lock.json": "{}",
        "node_modules/.keep": "",
    }
    if installed_bin:
        files[f"node_modules/.bin/{framework}"] = "#!/bin/sh\n"
    return files


def _reference(tmp_path: Path, size: tuple[int, int] = (320, 200)) -> Path:
    path = tmp_path / "design.png"
    Image.new("RGB", size, (255, 255, 255)).save(path)
    return path


def _state(reference: Path, **case: Any) -> dict[str, Any]:
    case_input = SimpleNamespace(
        repo_path=reference.parent,
        image_paths=[reference],
        visual_reference_paths=[],
        visual_check=True,
        **case,
    )
    return {"case_id": "C-001", "case_input": case_input, "generated_artifacts": None}


def _validator(
    tmp_path: Path,
    browser: Any,
    preview: FakePreviewLauncher | None,
    *,
    files: dict[str, str] | None = None,
    runner: ScriptedBuildRunner | None = None,
    **options: Any,
) -> RuntimeValidator:
    return RuntimeValidator(
        sandbox=ProjectSandbox(_project() if files is None else files),
        build_runner=runner or ScriptedBuildRunner(),
        playwright=browser,
        screenshot_diff=LocalScreenshotDiffAdapter(),
        preview=preview,
        visual_dir=tmp_path / "visual",
        **options,
    )


class TestPassingPage:
    async def test_matching_page_passes_and_leaves_evidence_files(self, tmp_path: Path) -> None:
        preview = FakePreviewLauncher()
        validator = _validator(tmp_path, PaintingBrowser(), preview)

        report, visual = await validator.run(_state(_reference(tmp_path)))

        assert visual is not None and visual.pass_result
        assert visual.ssim_score == 1.0
        assert visual.threshold == 0.92
        assert (tmp_path / "visual" / "generated.png").is_file()
        assert visual.generated_path == str(tmp_path / "visual" / "generated.png")
        assert [s.status for s in report.steps if s.name == "visual"] == ["passed"]
        assert report.failures == []

    async def test_preview_runs_inside_the_sandbox_and_is_stopped_before_cleanup(
        self, tmp_path: Path
    ) -> None:
        preview = FakePreviewLauncher()

        await _validator(tmp_path, PaintingBrowser(), preview).run(_state(_reference(tmp_path)))

        command, cwd = preview.started[0]
        assert command[:6] == ["npm", "exec", "--no", "--", "vite", "preview"]
        assert preview.cwd_existed_at_start is True
        assert preview.cwd_existed_at_stop is True
        assert preview.stopped == 1
        assert not cwd.exists()


class TestMismatch:
    async def test_different_page_fails_with_regions_diff_image_and_a_visual_failure(
        self, tmp_path: Path
    ) -> None:
        browser = PaintingBrowser(box=((40, 40, 239, 159), (0, 0, 0)))
        validator = _validator(tmp_path, browser, FakePreviewLauncher())

        report, visual = await validator.run(_state(_reference(tmp_path)))

        assert visual is not None and not visual.pass_result
        assert visual.ssim_score < 0.92
        assert len(visual.mismatch_regions) == 1
        region = visual.mismatch_regions[0]
        assert region.x <= 40 and region.y <= 40
        assert region.x + region.width >= 240 and region.y + region.height >= 160
        assert region.severity == "high"
        assert visual.diff_image_path is not None and Path(visual.diff_image_path).is_file()
        assert 0.0 < visual.changed_pixel_ratio < 1.0

        (failure,) = report.failures
        assert failure.source == "visual"
        assert failure.taxonomy_id == "FT-VISUAL-001"
        assert failure.severity == "major"
        assert "SSIM" in failure.message and "0.92" in failure.message
        assert [s.status for s in report.steps if s.name == "visual"] == ["failed"]

    async def test_threshold_is_configurable(self, tmp_path: Path) -> None:
        browser = PaintingBrowser(box=((0, 0, 31, 31), (0, 0, 0)))
        validator = _validator(tmp_path, browser, FakePreviewLauncher(), ssim_threshold=0.5)

        _, visual = await validator.run(_state(_reference(tmp_path)))

        assert visual is not None and visual.pass_result
        assert visual.threshold == 0.5

    async def test_reference_prefers_explicit_visual_references(self, tmp_path: Path) -> None:
        design = _reference(tmp_path)
        explicit = tmp_path / "explicit.png"
        Image.new("RGB", (320, 200), (0, 0, 0)).save(explicit)
        state = _state(design)
        state["case_input"].visual_reference_paths = [explicit]

        _, visual = await _validator(tmp_path, PaintingBrowser(), FakePreviewLauncher()).run(state)

        assert visual is not None and visual.reference_path == str(explicit)
        assert not visual.pass_result


class TestMismatchShare:
    async def test_small_areas_that_differ_fail_even_when_the_mean_score_is_high(
        self, tmp_path: Path
    ) -> None:
        # about 5% of the page differs: mean SSIM stays above 0.92, the mismatching share does not
        browser = PaintingBrowser(box=((64, 48, 127, 95), (0, 0, 0)), size=(320, 200))
        validator = _validator(tmp_path, browser, FakePreviewLauncher())

        report, visual = await validator.run(_state(_reference(tmp_path)))

        assert visual is not None
        assert visual.ssim_score >= 0.92
        assert visual.mismatch_area_ratio == pytest.approx(0.048)
        assert visual.max_mismatch_ratio == 0.03
        assert not visual.pass_result
        assert "4.8%" in report.failures[0].message

    async def test_the_allowed_share_is_configurable(self, tmp_path: Path) -> None:
        browser = PaintingBrowser(box=((64, 48, 127, 95), (0, 0, 0)))
        validator = _validator(tmp_path, browser, FakePreviewLauncher(), max_mismatch_ratio=0.10)

        _, visual = await validator.run(_state(_reference(tmp_path)))

        assert visual is not None and visual.pass_result


class TestBrowserFindings:
    async def test_console_errors_and_failed_requests_become_runtime_failures(
        self, tmp_path: Path
    ) -> None:
        browser = PaintingBrowser(
            console_errors=[ConsoleEntry(level="error", message="TypeError: x is undefined")],
            failed_requests=[FailedRequestEntry(url="http://x/api", failure_text="HTTP 500")],
        )

        report, visual = await _validator(tmp_path, browser, FakePreviewLauncher()).run(
            _state(_reference(tmp_path))
        )

        assert visual is not None and visual.pass_result
        assert sorted(f.source or "" for f in report.failures) == ["runtime", "runtime"]
        assert "TypeError: x is undefined" in report.runtime_errors
        assert "HTTP 500" in report.runtime_errors


class TestViewport:
    @pytest.mark.parametrize(
        ("size", "expected"),
        [((1000, 700), (1000, 700)), ((2880, 1800), (1440, 900)), ((100, 80), (320, 200))],
    )
    async def test_viewport_follows_the_reference_size(
        self, tmp_path: Path, size: tuple[int, int], expected: tuple[int, int]
    ) -> None:
        browser = PaintingBrowser(size=size)

        await _validator(tmp_path, browser, FakePreviewLauncher()).run(
            _state(_reference(tmp_path, size))
        )

        assert browser.viewports == [expected]


class TestNotApplicable:
    async def test_failed_build_is_not_previewed(self, tmp_path: Path) -> None:
        runner = ScriptedBuildRunner(
            {BUILD: CommandResult(returncode=1, stdout="", stderr="boom", duration_ms=1)}
        )
        preview = FakePreviewLauncher()

        report, visual = await _validator(tmp_path, PaintingBrowser(), preview, runner=runner).run(
            _state(_reference(tmp_path))
        )

        assert visual is None and preview.started == []
        step = next(s for s in report.steps if s.name == "visual")
        assert step.status == "skipped" and "build" in step.summary
        assert report.environment_issues == []

    async def test_waived_check_is_skipped(self, tmp_path: Path) -> None:
        state = _state(_reference(tmp_path))
        state["case_input"].visual_check = False
        preview = FakePreviewLauncher()

        report, visual = await _validator(tmp_path, PaintingBrowser(), preview).run(state)

        assert visual is None and preview.started == []
        step = next(s for s in report.steps if s.name == "visual")
        assert step.status == "skipped" and "waived" in step.summary

    async def test_null_browser_is_skipped(self, tmp_path: Path) -> None:
        browser = PaintingBrowser()
        browser.is_null = True

        report, visual = await _validator(tmp_path, browser, FakePreviewLauncher()).run(
            _state(_reference(tmp_path))
        )

        assert visual is None
        step = next(s for s in report.steps if s.name == "visual")
        assert step.status == "skipped" and "browser" in step.summary

    async def test_without_a_preview_launcher_nothing_changes(self, tmp_path: Path) -> None:
        report, visual = await _validator(tmp_path, PaintingBrowser(), None).run(
            _state(_reference(tmp_path))
        )

        assert visual is None
        assert all(s.name != "visual" for s in report.steps)


class TestUnavailable:
    async def test_unsupported_framework_is_an_environment_issue(self, tmp_path: Path) -> None:
        preview = FakePreviewLauncher()
        files = _project(framework="react-scripts")

        report, visual = await _validator(tmp_path, PaintingBrowser(), preview, files=files).run(
            _state(_reference(tmp_path))
        )

        assert visual is None and preview.started == []
        assert report.environment_issues and report.environment_issues[0].startswith("visual:")
        assert "vite" in report.environment_issues[0]

    async def test_missing_browser_is_an_environment_issue_and_preview_is_stopped(
        self, tmp_path: Path
    ) -> None:
        preview = FakePreviewLauncher()
        browser = PaintingBrowser(unavailable="Chromium for Playwright is not installed")

        report, visual = await _validator(tmp_path, browser, preview).run(
            _state(_reference(tmp_path))
        )

        assert visual is None and preview.stopped == 1
        assert "Chromium for Playwright is not installed" in report.environment_issues[0]

    async def test_preview_that_cannot_start_is_an_environment_issue(self, tmp_path: Path) -> None:
        preview = FakePreviewLauncher(fail_with="preview server exited with code 1: bad config")

        report, visual = await _validator(tmp_path, PaintingBrowser(), preview).run(
            _state(_reference(tmp_path))
        )

        assert visual is None
        assert "bad config" in report.environment_issues[0]


class TestRoundsKept:
    async def test_each_validation_keeps_its_own_screenshots_and_numbers(
        self, tmp_path: Path
    ) -> None:
        browser = PaintingBrowser(box=((40, 40, 239, 159), (0, 0, 0)))
        validator = _validator(tmp_path, browser, FakePreviewLauncher())
        state = _state(_reference(tmp_path))

        await validator.run(state)
        browser.box = None
        await validator.run(state)

        first, second = tmp_path / "visual" / "round-1", tmp_path / "visual" / "round-2"
        for folder in (first, second):
            assert sorted(p.name for p in folder.iterdir()) == [
                "diff.png",
                "generated.png",
                "report.json",
            ]
        before = VisualRegressionReport.model_validate_json((first / "report.json").read_text())
        after = VisualRegressionReport.model_validate_json((second / "report.json").read_text())
        assert not before.pass_result and after.pass_result
        assert before.ssim_score < after.ssim_score
        assert (first / "generated.png").read_bytes() != (second / "generated.png").read_bytes()
        # the top-level files still show the latest round
        latest = (tmp_path / "visual" / "generated.png").read_bytes()
        assert latest == (second / "generated.png").read_bytes()

    async def test_rounds_of_an_earlier_run_are_removed(self, tmp_path: Path) -> None:
        stale = tmp_path / "visual" / "round-3"
        stale.mkdir(parents=True)
        (stale / "report.json").write_text("{}")

        await _validator(tmp_path, PaintingBrowser(), FakePreviewLauncher()).run(
            _state(_reference(tmp_path))
        )

        assert not stale.exists()
        assert (tmp_path / "visual" / "round-1" / "report.json").is_file()

    async def test_nothing_is_kept_when_the_page_could_not_be_compared(
        self, tmp_path: Path
    ) -> None:
        browser = PaintingBrowser(unavailable="no browser")

        await _validator(tmp_path, browser, FakePreviewLauncher()).run(_state(_reference(tmp_path)))

        assert not list((tmp_path / "visual").glob("round-*"))

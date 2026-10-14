"""RuntimeValidator — sandbox orchestration for VALID-01, VALID-02, VALID-03."""

from __future__ import annotations

import contextlib
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from ddk.adapters.chromium_browser import BrowserUnavailableError
from ddk.adapters.preview import PreviewLauncher, PreviewStartError
from ddk.models.validation import (
    FailureRecord,
    FailureSource,
    RuntimeValidationReport,
    StepName,
    StepStatus,
    ValidationStep,
)
from ddk.models.visual import MismatchRegion, VisualRegressionReport
from ddk.security.repo_paths import resolve_within_repository
from ddk.services.diagnostics import Diagnostic, parse_diagnostics, strip_ansi
from ddk.services.failure_classifier import FailureClassifier
from ddk.services.toolchain import (
    SkippedStep,
    ToolchainPlan,
    ToolStep,
    plan_preview,
    plan_toolchain,
)

_SSIM_THRESHOLD = 0.92
_MAX_MISMATCH_RATIO = 0.03
_MAX_FAILURES = 50
_BROWSER_WAIT_MS = 2000
_MIN_VIEWPORT = (320, 200)
_MAX_VIEWPORT = (1920, 1200)
_HIGH_DISSIMILARITY = 75
_MEDIUM_DISSIMILARITY = 50
_TAIL_LINES = 8
_CHECKS: tuple[StepName, ...] = ("build", "typecheck", "lint")
_MISSING_TOOL_EXIT_CODES = frozenset({126, 127})
_MISSING_TOOL_OUTPUT = re.compile(
    r"npx canceled due to missing packages|could not determine executable to run"
    r"|command not found|command not allowed",
    re.IGNORECASE,
)


class RuntimeValidator:
    """Orchestrates sandbox validation, Playwright checks, and SSIM comparison."""

    def __init__(
        self,
        sandbox: Any,
        build_runner: Any,
        playwright: Any,
        screenshot_diff: Any,
        classifier: FailureClassifier | None = None,
        *,
        install_dependencies: bool = False,
        step_timeout_s: int = 300,
        install_timeout_s: int = 900,
        preview: PreviewLauncher | None = None,
        visual_dir: Path | None = None,
        ssim_threshold: float = _SSIM_THRESHOLD,
        max_mismatch_ratio: float = _MAX_MISMATCH_RATIO,
        preview_timeout_s: float = 60.0,
    ) -> None:
        self._sandbox = sandbox
        self._build = build_runner
        self._playwright = playwright
        self._screenshot_diff = screenshot_diff
        self._classifier = classifier or FailureClassifier()
        self._install = install_dependencies
        self._step_timeout = step_timeout_s
        self._install_timeout = install_timeout_s
        self._preview = preview
        self._visual_dir = visual_dir
        self._ssim_threshold = ssim_threshold
        self._max_mismatch = max_mismatch_ratio
        self._preview_timeout = preview_timeout_s
        self._rounds = 0  # screenshot comparisons made so far by this validator

    async def run(
        self,
        state: dict[str, Any],
        dev_server_url: str | None = None,
        reference_screenshot: Path | None = None,
        generated_screenshot: Path | None = None,
    ) -> tuple[RuntimeValidationReport, VisualRegressionReport | None]:
        case_id: str = state["case_id"]
        start_ms = int(time.monotonic() * 1000)
        runtime_errors: list[str] = []
        case_input = state.get("case_input")
        repo_path = (
            Path(case_input.repo_path)
            if case_input is not None and getattr(case_input, "repo_path", None) is not None
            else Path(".")
        )
        sandbox_dir = await self._sandbox.create(repo_path)
        visual: VisualRegressionReport | None = None

        try:
            self._materialize_generated_artifacts(state, sandbox_dir)
            steps, failures = await self._run_toolchain(sandbox_dir)
            if self._preview is not None and self._visual_dir is not None:
                visual = await self._run_visual(
                    case_id, case_input, sandbox_dir, steps, failures, runtime_errors
                )
        finally:
            await self._sandbox.cleanup()

        # --- Playwright ---
        if dev_server_url is not None:
            for entry in await self._playwright.get_console_errors(dev_server_url):
                runtime_errors.append(entry.message)
                failures.append(self._runtime_failure(entry.message))

            for req in await self._playwright.get_failed_requests(
                dev_server_url, correlation_id=case_id
            ):
                runtime_errors.append(req.failure_text)
                failures.append(self._runtime_failure(req.failure_text))

        duration_ms = int(time.monotonic() * 1000) - start_ms
        report = RuntimeValidationReport(
            case_id=case_id,
            build_success=_succeeded(steps, "build"),
            type_check_success=_succeeded(steps, "typecheck"),
            lint_success=_succeeded(steps, "lint"),
            runtime_errors=runtime_errors,
            failures=failures,
            steps=steps,
            duration_ms=duration_ms,
        )

        # --- SSIM (explicit screenshots) ---
        vis_report: VisualRegressionReport | None = visual
        if reference_screenshot is not None and generated_screenshot is not None:
            ssim_result = self._screenshot_diff.compute_ssim(
                reference_screenshot, generated_screenshot
            )
            vis_report = VisualRegressionReport(
                case_id=case_id,
                reference_path=str(reference_screenshot),
                generated_path=str(generated_screenshot),
                ssim_score=ssim_result.score,
                threshold=self._ssim_threshold,
                pass_result=ssim_result.score >= self._ssim_threshold,
            )

        return report, vis_report

    # ------------------------------------------------------------------
    # Visual evidence
    # ------------------------------------------------------------------

    async def _run_visual(
        self,
        case_id: str,
        case_input: Any,
        sandbox_dir: Path,
        steps: list[ValidationStep],
        failures: list[FailureRecord],
        runtime_errors: list[str],
    ) -> VisualRegressionReport | None:
        """Serve the built app, look at it in a browser, compare it with the design image."""
        started = time.monotonic()

        def finish(status: StepStatus, summary: str) -> None:
            steps.append(
                ValidationStep(
                    name="visual",
                    status=status,
                    summary=summary,
                    duration_ms=int((time.monotonic() - started) * 1000),
                )
            )

        if not getattr(case_input, "visual_check", True):
            finish("skipped", "visual check waived for this run")
            return None
        if getattr(self._playwright, "is_null", False):
            finish("skipped", "no browser configured")
            return None
        reference = _reference_image(case_input)
        if reference is None or not reference.is_file():
            finish("unavailable", f"reference image not found: {reference}")
            return None
        not_ready = _build_state(steps)
        if not_ready is not None:
            status, why = not_ready
            finish(status, why)
            return None
        plan = plan_preview(sandbox_dir)
        if plan.command is None:
            finish("unavailable", plan.reason)
            return None
        assert self._preview is not None and self._visual_dir is not None

        try:
            session = await self._preview.start(
                plan.command, sandbox_dir, timeout_s=self._preview_timeout
            )
        except PreviewStartError as exc:
            finish("unavailable", str(exc))
            return None

        self._visual_dir.mkdir(parents=True, exist_ok=True)
        generated = self._visual_dir / "generated.png"
        try:
            console = await self._playwright.get_console_errors(
                session.url, wait_ms=_BROWSER_WAIT_MS
            )
            requests = await self._playwright.get_failed_requests(
                session.url, wait_ms=_BROWSER_WAIT_MS, correlation_id=case_id
            )
            await self._playwright.capture_screenshot(
                session.url, generated, _viewport_for(reference)
            )
        except BrowserUnavailableError as exc:
            finish("unavailable", str(exc))
            return None
        finally:
            await session.stop()

        for message in [e.message for e in console] + [r.failure_text for r in requests]:
            runtime_errors.append(message)
            if len(failures) < _MAX_FAILURES:
                failures.append(self._runtime_failure(message))

        try:
            report = self._compare(case_id, reference, generated)
        except OSError as exc:
            finish("unavailable", f"cannot compare screenshots: {exc}")
            return None
        with contextlib.suppress(OSError):  # the kept copies are evidence for the report only
            self._keep_round(report)
        if report.pass_result:
            finish(
                "passed",
                f"SSIM {report.ssim_score:.2f} (min {report.threshold:.2f}), "
                f"{report.mismatch_area_ratio:.1%} of the page differs "
                f"(max {report.max_mismatch_ratio:.1%})",
            )
        else:
            failures.append(_visual_failure(report))
            finish("failed", _visual_message(report))
        return report

    def _keep_round(self, report: VisualRegressionReport) -> None:
        """Copy this comparison to ``round-N/``; the top-level files are overwritten each round."""
        assert self._visual_dir is not None
        if self._rounds == 0:
            for earlier in self._visual_dir.glob("round-*"):
                shutil.rmtree(earlier, ignore_errors=True)
        self._rounds += 1
        folder = self._visual_dir / f"round-{self._rounds}"
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report.generated_path, folder / "generated.png")
        if report.diff_image_path is not None:
            shutil.copy2(report.diff_image_path, folder / "diff.png")
        (folder / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")

    def _compare(self, case_id: str, reference: Path, generated: Path) -> VisualRegressionReport:
        assert self._visual_dir is not None
        result = self._screenshot_diff.compute_ssim(reference, generated)
        diff_path = self._screenshot_diff.generate_diff_image(
            reference, generated, self._visual_dir / "diff.png"
        )
        with Image.open(reference) as image:
            width, height = _viewport_for_size(image.size)
        mismatch = float(getattr(result, "mismatch_area_ratio", 0.0))
        return VisualRegressionReport(
            case_id=case_id,
            reference_path=str(reference),
            generated_path=str(generated),
            ssim_score=result.score,
            threshold=self._ssim_threshold,
            pass_result=result.score >= self._ssim_threshold and mismatch <= self._max_mismatch,
            mismatch_regions=[_region(r) for r in result.mismatch_regions],
            diff_image_path=str(diff_path),
            changed_pixel_ratio=getattr(result, "changed_pixel_ratio", 0.0),
            mismatch_area_ratio=mismatch,
            max_mismatch_ratio=self._max_mismatch,
            viewport=f"{width}x{height}",
        )

    # ------------------------------------------------------------------
    # Toolchain steps
    # ------------------------------------------------------------------

    async def _run_toolchain(
        self, sandbox_dir: Path
    ) -> tuple[list[ValidationStep], list[FailureRecord]]:
        plan = plan_toolchain(sandbox_dir)
        steps: list[ValidationStep] = []
        failures: list[FailureRecord] = []
        seen: set[tuple[str | None, int | None, str | None, str]] = set()

        blocked = await self._prepare_dependencies(plan, sandbox_dir, steps)

        for name in _CHECKS:
            planned = [step for step in plan.steps if step.name == name]
            if not planned:
                steps.append(_skipped_step(name, plan.skipped))
                continue
            for tool_step in planned:
                if blocked is not None:
                    steps.append(
                        ValidationStep(
                            name=name,
                            command=tool_step.command,
                            status="unavailable",
                            summary=blocked,
                        )
                    )
                    continue
                steps.append(await self._run_step(tool_step, sandbox_dir, failures, seen))
        return steps, failures

    async def _prepare_dependencies(
        self, plan: ToolchainPlan, sandbox_dir: Path, steps: list[ValidationStep]
    ) -> str | None:
        """Install dependencies when needed and allowed; return why checks cannot run, if so."""
        if not plan.needs_install or plan.install_command is None:
            return None
        command_line = " ".join(plan.install_command)
        if not self._install:
            return f"dependencies are not installed; run `{command_line}` or pass --install"

        result = await self._build.run(
            plan.install_command, cwd=sandbox_dir, timeout=self._install_timeout
        )
        output = f"{result.stdout}\n{result.stderr}"
        ok = result.returncode == 0
        steps.append(
            ValidationStep(
                name="install",
                command=plan.install_command,
                status="passed" if ok else "failed",
                returncode=result.returncode,
                duration_ms=result.duration_ms,
                summary="" if ok else _first_line(output),
            )
        )
        return None if ok else f"dependency install failed: {_first_line(output)}"

    async def _run_step(
        self,
        tool_step: ToolStep,
        sandbox_dir: Path,
        failures: list[FailureRecord],
        seen: set[tuple[str | None, int | None, str | None, str]],
    ) -> ValidationStep:
        result = await self._build.run(
            tool_step.command, cwd=sandbox_dir, timeout=self._step_timeout
        )
        base: dict[str, Any] = {
            "name": tool_step.name,
            "command": tool_step.command,
            "returncode": result.returncode,
            "duration_ms": result.duration_ms,
        }
        if result.returncode == 0:
            return ValidationStep(status="passed", **base)

        output = strip_ansi(f"{result.stdout}\n{result.stderr}")
        if result.returncode in _MISSING_TOOL_EXIT_CODES or _MISSING_TOOL_OUTPUT.search(output):
            return ValidationStep(status="unavailable", summary=_first_line(output), **base)

        diagnostics = parse_diagnostics(output, root=sandbox_dir)
        errors = [d for d in diagnostics if d.severity == "error"]
        records = [self._record(d, tool_step.name) for d in _unseen(errors, seen)]
        if not errors:
            records = [self._raw_record(tool_step.name, output)]

        room = max(0, _MAX_FAILURES - len(failures))
        failures.extend(records[:room])
        dropped = len(records) - room
        summary = f"{len(errors)} error(s)" if errors else _first_line(output)
        if dropped > 0:
            summary += f" (+{dropped} not listed)"
        return ValidationStep(
            status="failed",
            summary=summary,
            error_count=len(errors),
            warning_count=len(diagnostics) - len(errors),
            **base,
        )

    # ------------------------------------------------------------------
    # Failure records
    # ------------------------------------------------------------------

    def _record(self, diagnostic: Diagnostic, source: StepName) -> FailureRecord:
        text = (
            diagnostic.message
            if diagnostic.code is None
            else f"{diagnostic.message} ({diagnostic.code})"
        )
        where = ""
        if diagnostic.file_path is not None:
            where = f"{diagnostic.file_path}:{diagnostic.line or 0}:{diagnostic.column or 0} "
        record = self._classifier.classify(text, file_path=diagnostic.file_path)
        return record.model_copy(
            update={
                "message": diagnostic.message[:500],
                "line_number": diagnostic.line,
                "source": _failure_source(source),
                "code": diagnostic.code,
                "raw_output": f"{where}{text}",
            }
        )

    def _raw_record(self, source: StepName, output: str) -> FailureRecord:
        tail = "\n".join(_meaningful_lines(output)[-_TAIL_LINES:])
        record = self._classifier.classify(tail or f"{source} failed without output")
        return record.model_copy(update={"source": _failure_source(source)})

    def _runtime_failure(self, message: str) -> FailureRecord:
        record = self._classifier.classify(message)
        return record.model_copy(update={"source": "runtime"})

    # ------------------------------------------------------------------
    # Sandbox helpers
    # ------------------------------------------------------------------

    def _materialize_generated_artifacts(self, state: dict[str, Any], sandbox_dir: Path) -> None:
        """Write generated artifacts into the sandbox before validation begins."""
        generated_artifacts = state.get("generated_artifacts")
        if generated_artifacts is None:
            return

        for generated_file in generated_artifacts.files:
            output_path = resolve_within_repository(sandbox_dir, generated_file.path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(generated_file.content, encoding="utf-8")


def _succeeded(steps: list[ValidationStep], name: StepName) -> bool:
    return all(step.status in {"passed", "skipped"} for step in steps if step.name == name)


def _skipped_step(name: StepName, skipped: list[SkippedStep]) -> ValidationStep:
    reason = next((s.reason for s in skipped if s.name == name), "not applicable")
    return ValidationStep(name=name, status="skipped", summary=reason)


def _unseen(
    diagnostics: list[Diagnostic],
    seen: set[tuple[str | None, int | None, str | None, str]],
) -> list[Diagnostic]:
    fresh: list[Diagnostic] = []
    for diagnostic in diagnostics:
        key = (diagnostic.file_path, diagnostic.line, diagnostic.code, diagnostic.message)
        if key not in seen:
            seen.add(key)
            fresh.append(diagnostic)
    return fresh


def _failure_source(name: StepName) -> FailureSource | None:
    return None if name == "install" else name


def _meaningful_lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


def _first_line(output: str) -> str:
    lines = _meaningful_lines(strip_ansi(output))
    return lines[0][:200] if lines else "no output"


def _reference_image(case_input: Any) -> Path | None:
    explicit = list(getattr(case_input, "visual_reference_paths", None) or [])
    images = list(getattr(case_input, "image_paths", None) or [])
    chosen = explicit or images
    return Path(chosen[0]) if chosen else None


def _build_state(steps: list[ValidationStep]) -> tuple[StepStatus, str] | None:
    """Why the app cannot be previewed yet, or ``None`` when a build passed."""
    builds = [step for step in steps if step.name == "build"]
    if any(step.status == "failed" for step in builds):
        return "skipped", "build failed; fix it before the page is compared with the design"
    if any(step.status == "unavailable" for step in builds):
        return "skipped", "build could not run"
    if not any(step.status == "passed" for step in builds):
        return "unavailable", "no build step ran, so there is no built app to preview"
    return None


def _viewport_for_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    if width > _MAX_VIEWPORT[0]:
        width, height = width // 2, height // 2  # a wider design is taken as a 2x capture
    return (
        max(_MIN_VIEWPORT[0], min(width, _MAX_VIEWPORT[0])),
        max(_MIN_VIEWPORT[1], min(height, _MAX_VIEWPORT[1])),
    )


def _viewport_for(reference: Path) -> tuple[int, int]:
    with Image.open(reference) as image:
        return _viewport_for_size(image.size)


def _region(raw: dict[str, int]) -> MismatchRegion:
    dissimilarity = raw.get("dissimilarity", 100)
    severity = (
        "high"
        if dissimilarity >= _HIGH_DISSIMILARITY
        else "medium"
        if dissimilarity >= _MEDIUM_DISSIMILARITY
        else "low"
    )
    return MismatchRegion(
        x=raw["x"], y=raw["y"], width=raw["width"], height=raw["height"], severity=severity
    )


def _visual_message(report: VisualRegressionReport) -> str:
    text = (
        f"Rendered page does not match the design: SSIM {report.ssim_score:.2f} "
        f"(min {report.threshold:.2f}), {report.mismatch_area_ratio:.1%} of the page differs "
        f"(max {report.max_mismatch_ratio:.1%})"
    )
    if report.mismatch_regions:
        top = report.mismatch_regions[0]
        text += (
            f"; {len(report.mismatch_regions)} mismatching region(s), largest at "
            f"x={top.x} y={top.y} {top.width}x{top.height}"
        )
    return text


def _visual_failure(report: VisualRegressionReport) -> FailureRecord:
    regions = "\n".join(
        f"- x={r.x} y={r.y} {r.width}x{r.height} ({r.severity})" for r in report.mismatch_regions
    )
    return FailureRecord(
        id=str(uuid.uuid4()),
        taxonomy_id="FT-VISUAL-001",
        severity="major",
        message=_visual_message(report),
        raw_output=f"changed pixels: {report.changed_pixel_ratio:.1%}\n{regions}".strip(),
        source="visual",
        code="SSIM",
    )

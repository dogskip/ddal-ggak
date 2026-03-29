"""RuntimeValidator — sandbox orchestration for VALID-01, VALID-02, VALID-03."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport
from ddk.services.failure_classifier import FailureClassifier

_SSIM_THRESHOLD = 0.92


class RuntimeValidator:
    """Orchestrates sandbox validation, Playwright checks, and SSIM comparison."""

    def __init__(
        self,
        sandbox: Any,
        build_runner: Any,
        playwright: Any,
        screenshot_diff: Any,
        classifier: FailureClassifier | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._build = build_runner
        self._playwright = playwright
        self._screenshot_diff = screenshot_diff
        self._classifier = classifier or FailureClassifier()

    async def run(
        self,
        state: dict[str, Any],
        dev_server_url: str | None = None,
        reference_screenshot: Path | None = None,
        generated_screenshot: Path | None = None,
    ) -> tuple[RuntimeValidationReport, VisualRegressionReport | None]:
        case_id: str = state["case_id"]
        start_ms = int(time.monotonic() * 1000)
        failures: list[FailureRecord] = []
        runtime_errors: list[str] = []

        sandbox_dir = Path("/tmp/ddk-sandbox")

        # --- Build ---
        build_result = await self._build.run(["npm", "run", "build"], cwd=sandbox_dir)
        build_success = build_result.returncode == 0
        if not build_success and build_result.stderr:
            failures.append(self._classifier.classify(build_result.stderr))

        # --- TypeCheck ---
        tc_result = await self._build.run(["npx", "tsc", "--noEmit"], cwd=sandbox_dir)
        type_check_success = tc_result.returncode == 0
        if not type_check_success and tc_result.stderr:
            failures.append(self._classifier.classify(tc_result.stderr))

        # --- Lint ---
        lint_result = await self._build.run(["npx", "eslint", "."], cwd=sandbox_dir)
        lint_success = lint_result.returncode == 0
        if not lint_success and lint_result.stderr:
            failures.append(self._classifier.classify(lint_result.stderr))

        # --- Playwright ---
        if dev_server_url is not None:
            for entry in await self._playwright.get_console_errors(dev_server_url):
                runtime_errors.append(entry.message)
                failures.append(self._classifier.classify(entry.message))

            for req in await self._playwright.get_failed_requests(
                dev_server_url, correlation_id=case_id
            ):
                runtime_errors.append(req.failure_text)
                failures.append(self._classifier.classify(req.failure_text))

        duration_ms = int(time.monotonic() * 1000) - start_ms
        report = RuntimeValidationReport(
            case_id=case_id,
            build_success=build_success,
            type_check_success=type_check_success,
            lint_success=lint_success,
            runtime_errors=runtime_errors,
            failures=failures,
            duration_ms=duration_ms,
        )

        # --- SSIM ---
        vis_report: VisualRegressionReport | None = None
        if reference_screenshot is not None and generated_screenshot is not None:
            ssim_result = self._screenshot_diff.compute_ssim(
                reference_screenshot, generated_screenshot
            )
            vis_report = VisualRegressionReport(
                case_id=case_id,
                reference_path=str(reference_screenshot),
                generated_path=str(generated_screenshot),
                ssim_score=ssim_result.score,
                threshold=_SSIM_THRESHOLD,
                pass_result=ssim_result.score >= _SSIM_THRESHOLD,
            )

        return report, vis_report

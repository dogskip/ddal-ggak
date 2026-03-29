"""RuntimeValidator unit tests — Wave 2 TDD (7 tests).

asyncio_mode = "auto" in pyproject.toml — no @pytest.mark.asyncio needed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ddk.adapters.playwright_browser import ConsoleEntry, FailedRequestEntry
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.validation import FAILURE_TAXONOMY
from ddk.services.runtime_validator import RuntimeValidator
from tests.fakes import (
    FakeBuildRunner,
    FakePlaywrightAdapter,
    FakeSSIMAdapter,
    TempDirSandbox,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_state(case_id: str = "test-case") -> dict[str, Any]:
    return {"case_id": case_id, "generated_artifacts": None}


def make_validator(
    *,
    build_runner: FakeBuildRunner | None = None,
    playwright: FakePlaywrightAdapter | None = None,
    screenshot_diff: FakeSSIMAdapter | None = None,
    ) -> RuntimeValidator:
    return RuntimeValidator(
        sandbox=TempDirSandbox(),
        build_runner=build_runner or FakeBuildRunner(),
        playwright=playwright or FakePlaywrightAdapter(),
        screenshot_diff=screenshot_diff or FakeSSIMAdapter(),
    )


class NoCleanupSandbox(TempDirSandbox):
    async def cleanup(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSuccessPath:
    async def test_validate_success_returns_passing_report(self) -> None:
        validator = make_validator(build_runner=FakeBuildRunner(returncode=0))
        report, _ = await validator.run(make_state())
        assert report.build_success is True
        assert report.type_check_success is True
        assert report.lint_success is True
        assert report.failures == []

    async def test_validate_materializes_generated_files_in_sandbox(self, tmp_path: Path) -> None:
        validator = RuntimeValidator(
            sandbox=NoCleanupSandbox(),
            build_runner=FakeBuildRunner(returncode=0),
            playwright=FakePlaywrightAdapter(),
            screenshot_diff=FakeSSIMAdapter(),
        )
        state = {
            "case_id": "test-case",
            "case_input": SimpleNamespace(repo_path=tmp_path),
            "generated_artifacts": GeneratedArtifactSet(
                case_id="test-case",
                files=[
                    GeneratedFile(
                        path="src/components/Button.tsx",
                        content="export const Button = () => null;",
                        language="typescript",
                        source_node_id="node-btn",
                        is_new=True,
                    )
                ],
                file_map={"src/components/Button.tsx": "export const Button = () => null;"},
                generation_trace=["node-btn:src/components/Button.tsx"],
                changed_paths=["src/components/Button.tsx"],
            ),
        }

        await validator.run(state)

        assert len(validator._build.run_log) == 3  # type: ignore[attr-defined]
        materialized = Path(validator._build.run_log[0]["cwd"]) / "src/components/Button.tsx"  # type: ignore[attr-defined]
        assert materialized.exists()


class TestBuildFailure:
    async def test_validate_build_failure_captures_ft_build_001(self) -> None:
        validator = make_validator(
            build_runner=FakeBuildRunner(
                returncode=1, stderr="Cannot find module './Button'"
            )
        )
        report, _ = await validator.run(make_state())
        assert report.build_success is False
        assert any(f.taxonomy_id == "FT-BUILD-001" for f in report.failures)

    async def test_validate_syntax_error_has_valid_taxonomy_id(self) -> None:
        validator = make_validator(
            build_runner=FakeBuildRunner(
                returncode=1, stderr="SyntaxError: Unexpected token"
            )
        )
        report, _ = await validator.run(make_state())
        assert len(report.failures) > 0
        for f in report.failures:
            assert f.taxonomy_id in FAILURE_TAXONOMY or f.taxonomy_id == "FT-UNKNOWN"


class TestPlaywright:
    async def test_validate_playwright_console_errors_captured(self) -> None:
        errors = [ConsoleEntry(level="error", message="Uncaught TypeError: foo is null")]
        validator = make_validator(
            playwright=FakePlaywrightAdapter(console_errors=errors)
        )
        report, _ = await validator.run(
            make_state(), dev_server_url="http://localhost:3000"
        )
        assert len(report.runtime_errors) > 0

    async def test_validate_playwright_failed_requests_ft_runtime_003(self) -> None:
        reqs = [
            FailedRequestEntry(
                url="http://api/data",
                failure_text="net::ERR_CONNECTION_REFUSED",
            )
        ]
        validator = make_validator(
            playwright=FakePlaywrightAdapter(failed_requests=reqs)
        )
        report, _ = await validator.run(
            make_state(), dev_server_url="http://localhost:3000"
        )
        assert any(f.taxonomy_id == "FT-RUNTIME-003" for f in report.failures)


class TestSSIM:
    async def test_validate_ssim_below_threshold_marks_visual_failure(self) -> None:
        validator = make_validator(screenshot_diff=FakeSSIMAdapter(ssim_score=0.85))
        _, vis = await validator.run(
            make_state(),
            reference_screenshot=Path("/tmp/ref.png"),
            generated_screenshot=Path("/tmp/gen.png"),
        )
        assert vis is not None
        assert vis.pass_result is False
        assert vis.ssim_score == pytest.approx(0.85)

    async def test_validate_ssim_above_threshold_passes(self) -> None:
        validator = make_validator(screenshot_diff=FakeSSIMAdapter(ssim_score=0.95))
        _, vis = await validator.run(
            make_state(),
            reference_screenshot=Path("/tmp/ref.png"),
            generated_screenshot=Path("/tmp/gen.png"),
        )
        assert vis is not None
        assert vis.pass_result is True

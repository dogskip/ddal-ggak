"""TDD tests for B1-B9 deployment blockers.

Each test documents the expected FIXED behavior.
Tests are written BEFORE fixes — they must FAIL on the current codebase
and PASS after all blocker fixes are applied.
"""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.null_playwright import NullPlaywrightAdapter
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport
from ddk.services.auto_fix_planner import AutoFixPlanner
from ddk.services.release_gate import ReleaseGate
from ddk.services.scorecard_calculator import ScorecardCalculator

# ──────────────────────────────────────────────
# B1: Release Gate — empty state must NOT pass
# ──────────────────────────────────────────────


class TestB1ScorecardEmptyState:
    """Scorecard must score 0.0 when validation evidence is missing."""

    def _empty_state(self) -> dict:
        return {
            "case_id": "test-case",
            "runtime_validation_report": None,
            "visual_regression_report": None,
            "normalization_report": None,
            "fix_attempts": [],
            "terminal_state": None,
            "retry_budget_remaining": 3,
        }

    def test_precision_zero_without_runtime(self):
        calc = ScorecardCalculator()
        sc = calc.calculate(self._empty_state())
        assert sc.precision == 0.0, "precision must be 0.0 when runtime evidence is missing"

    def test_automation_zero_without_runtime(self):
        calc = ScorecardCalculator()
        sc = calc.calculate(self._empty_state())
        assert sc.automation == 0.0, "automation must be 0.0 when runtime evidence is missing"

    def test_overall_below_threshold(self):
        calc = ScorecardCalculator()
        sc = calc.calculate(self._empty_state())
        assert sc.overall < 0.85, "overall must be below release threshold without evidence"

    def test_grade_not_a(self):
        calc = ScorecardCalculator()
        sc = calc.calculate(self._empty_state())
        assert sc.grade != "A", "grade must not be A without evidence"

    def test_precision_high_with_clean_runtime(self):
        """When runtime passes cleanly, precision should be high."""
        calc = ScorecardCalculator()
        state = self._empty_state()
        state["runtime_validation_report"] = RuntimeValidationReport(
            case_id="test-case",
            build_success=True,
            type_check_success=True,
            lint_success=True,
        )
        sc = calc.calculate(state)
        assert sc.precision == 1.0


class TestB1ReleaseGateEmptyState:
    """Release gate must block when no validation evidence exists."""

    def _empty_state(self) -> dict:
        return {
            "case_id": "test-case",
            "runtime_validation_report": None,
            "visual_regression_report": None,
            "normalization_report": None,
            "fix_attempts": [],
            "terminal_state": None,
            "retry_budget_remaining": 3,
        }

    def test_gate_blocks_without_evidence(self):
        gate = ReleaseGate()
        calc = ScorecardCalculator()
        state = self._empty_state()
        sc = calc.calculate(state)
        decision = gate.decide(state, sc)
        assert decision.decision != "ready", "must not be 'ready' without runtime evidence"

    def test_gate_has_missing_evidence_blocker(self):
        gate = ReleaseGate()
        calc = ScorecardCalculator()
        state = self._empty_state()
        sc = calc.calculate(state)
        decision = gate.decide(state, sc)
        blocker_ids = [b.id for b in decision.blockers]
        assert any("missing" in bid.lower() or "evidence" in bid.lower() for bid in blocker_ids), (
            f"must have a missing-evidence blocker, got: {blocker_ids}"
        )

    def test_gate_ready_with_clean_runtime(self):
        """Gate should approve when runtime passes cleanly."""
        gate = ReleaseGate()
        calc = ScorecardCalculator()
        state = self._empty_state()
        state["runtime_validation_report"] = RuntimeValidationReport(
            case_id="test-case",
            build_success=True,
            type_check_success=True,
            lint_success=True,
        )
        sc = calc.calculate(state)
        decision = gate.decide(state, sc)
        assert decision.decision == "ready"


# ──────────────────────────────────────────────
# B2: Sandbox Policy Enforcement
# ──────────────────────────────────────────────


class TestB2SandboxPolicy:
    """TempDirSandbox.run_command must enforce policy."""

    @pytest.fixture
    def sandbox(self, tmp_path: Path):
        sb = TempDirSandbox()
        sb._sandbox_path = tmp_path
        return sb

    @pytest.mark.asyncio
    async def test_disallowed_command_rejected(self, sandbox: TempDirSandbox):
        result = await sandbox.run_command(["curl", "http://evil.com"])
        assert result.returncode != 0, "disallowed command must fail"
        assert "not allowed" in result.stderr.lower() or "denied" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_allowed_command_accepted(self, sandbox: TempDirSandbox, tmp_path: Path):
        # Create a minimal package.json so `node -e` works
        (tmp_path / "test.js").write_text("console.log('ok')")
        result = await sandbox.run_command(["node", "-e", "console.log('ok')"], cwd=tmp_path)
        # May fail if node not installed, but shouldn't be policy-rejected
        assert "not allowed" not in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_empty_command_rejected(self, sandbox: TempDirSandbox):
        result = await sandbox.run_command([])
        assert result.returncode != 0


# ──────────────────────────────────────────────
# B3: Visual Validation Default Path
# ──────────────────────────────────────────────


class TestB3NullPlaywrightSkipped:
    """NullPlaywright results must be marked as skipped, not passed."""

    @pytest.mark.asyncio
    async def test_console_errors_marked_skipped(self):
        adapter = NullPlaywrightAdapter()
        await adapter.get_console_errors("http://localhost:3000")
        # The adapter should indicate it's a null/skipped result
        assert hasattr(adapter, "is_null") and adapter.is_null is True

    def test_scorecard_penalizes_skipped_visual(self):
        """Scorecard precision should be reduced when visual is skipped (None)
        but runtime exists — this means visual evidence is incomplete."""
        calc = ScorecardCalculator()
        state = {
            "case_id": "test",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="test",
                build_success=True,
                type_check_success=True,
                lint_success=True,
            ),
            "visual_regression_report": None,  # skipped
            "normalization_report": None,
            "fix_attempts": [],
            "terminal_state": None,
            "retry_budget_remaining": 3,
        }
        sc = calc.calculate(state)
        # When visual is skipped, scalability sub-score gets a small penalty
        assert sc.scalability < 1.0 or sc.details.get("visual_skipped") == "true"


# ──────────────────────────────────────────────
# B4: Auto-fix Artifact Application
# ──────────────────────────────────────────────


class TestB4AutoFixApplication:
    """AutoFixPlanner.plan_and_apply must actually modify artifacts."""

    @pytest.mark.asyncio
    async def test_r01_removes_unused_import(self):
        llm = AsyncMock()
        planner = AutoFixPlanner(llm)

        original_content = textwrap.dedent("""\
            import { useState } from 'react';
            import { unused } from './utils';

            export function App() { return <div/>; }
        """)
        artifacts = GeneratedArtifactSet(
            case_id="test",
            files=[
                GeneratedFile(
                    path="src/App.tsx",
                    content=original_content,
                    language="typescript",
                    source_node_id="n1",
                )
            ],
        )

        failures = [
            FailureRecord(
                id="f1",
                taxonomy_id="FT-LINT-001",
                severity="minor",
                message="'unused' is defined but never used",
                file_path="src/App.tsx",
            )
        ]

        attempt, new_artifacts = await planner.plan_and_apply(failures, artifacts, "test", 1)
        assert attempt.rule_id == "R-01"

        # The key assertion: artifact content must actually be modified
        modified_file = new_artifacts.files[0]
        assert "unused" not in modified_file.content, (
            "R-01 must actually remove the unused import from artifact content"
        )
        assert "useState" in modified_file.content  # other imports preserved

    @pytest.mark.asyncio
    async def test_r09_llm_applies_response(self):
        llm = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "fixed content here"
        llm.complete.return_value = mock_response
        planner = AutoFixPlanner(llm)

        artifacts = GeneratedArtifactSet(
            case_id="test",
            files=[
                GeneratedFile(
                    path="src/broken.ts",
                    content="broken code",
                    language="typescript",
                    source_node_id="n1",
                )
            ],
        )

        failures = [
            FailureRecord(
                id="f1",
                taxonomy_id="FT-BUILD-002",
                severity="critical",
                message="Syntax error",
                file_path="src/broken.ts",
                raw_output="Unexpected token",
            )
        ]

        attempt, new_artifacts = await planner.plan_and_apply(failures, artifacts, "test", 1)
        assert attempt.rule_id == "R-09"
        modified = new_artifacts.files[0]
        assert modified.content == "fixed content here", (
            "R-09 must apply LLM response to artifact content"
        )


# ──────────────────────────────────────────────
# B5: Rollback Untracked Cleanup
# ──────────────────────────────────────────────


class TestB5RollbackCleanup:
    """rollback_to must clean untracked files."""

    @pytest.fixture
    def git_repo(self, tmp_path: Path):
        """Create a temporary git repo with an initial commit."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True)
        (repo / "file.txt").write_text("initial")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)
        return repo

    @pytest.mark.asyncio
    async def test_rollback_cleans_untracked(self, git_repo: Path):

        # Create checkpoint
        adapter = LocalGitAdapter()
        ref = "refs/ddk/test/checkpoint"
        await adapter.create_checkpoint(git_repo, ref)

        # Add untracked file (simulates generated artifacts)
        (git_repo / "generated.ts").write_text("generated code")
        assert (git_repo / "generated.ts").exists()

        # Rollback
        await adapter.rollback_to(git_repo, ref, force=True)

        # Untracked file should be cleaned
        assert not (git_repo / "generated.ts").exists(), (
            "rollback_to must clean untracked files with git clean"
        )

    @pytest.mark.asyncio
    async def test_rollback_cleans_untracked_directories(self, git_repo: Path):
        adapter = LocalGitAdapter()
        ref = "refs/ddk/test/checkpoint"
        await adapter.create_checkpoint(git_repo, ref)

        # Add untracked directory
        (git_repo / "src").mkdir()
        (git_repo / "src" / "component.tsx").write_text("export default () => <div/>;")
        assert (git_repo / "src" / "component.tsx").exists()

        await adapter.rollback_to(git_repo, ref, force=True)
        assert not (git_repo / "src").exists(), "rollback_to must clean untracked directories"


# ──────────────────────────────────────────────
# B6: MCP Preflight False Negative
# ──────────────────────────────────────────────


class TestB6PreflightEnvLoading:
    """preflight() must load env vars, not bypass them."""

    def test_preflight_reads_env_var(self):
        from ddk.server import preflight

        with patch.dict(os.environ, {"DDK_ANTHROPIC_API_KEY": "sk-test-key-12345"}, clear=False):
            result_json = preflight()
            result = json.loads(result_json)
            checks = result["checks"]
            api_check = next((r for r in checks if r["check"] == "DDK_ANTHROPIC_API_KEY"), None)
            assert api_check is not None
            assert api_check["ok"] is True, "preflight must detect API key from environment"


# ──────────────────────────────────────────────
# B7: Version Alignment
# ──────────────────────────────────────────────


class TestB7VersionAlignment:
    """__version__ must match pyproject.toml."""

    def test_version_matches_pyproject(self):
        import ddk

        # pyproject.toml declares version = "1.0.0"
        assert ddk.__version__ == "1.0.0", (
            f"__version__ ({ddk.__version__}) must match pyproject.toml (1.0.0)"
        )


# ──────────────────────────────────────────────
# B8: Structured Logging Activation
# ──────────────────────────────────────────────


class TestB8LoggingActivation:
    """CLI and MCP entry points must call configure_logging."""

    def test_cli_callback_initializes_logging(self):
        """Verify the CLI callback calls configure_logging."""
        import contextlib

        from ddk.cli import main as cli_callback

        with patch("ddk.logging.setup.configure_logging") as mock_log:
            with contextlib.suppress(SystemExit, typer.Exit):
                cli_callback(log_level="INFO", output=Path("."))
            mock_log.assert_called_once()


# ──────────────────────────────────────────────
# B9: Regression — existing tests still pass
# ──────────────────────────────────────────────


class TestB9RegressionSafety:
    """Ensure core models and services still work after fixes."""

    def test_scorecard_model_valid(self):
        sc = Scorecard(
            case_id="test",
            precision=0.95,
            maintainability=0.90,
            automation=0.85,
            scalability=0.80,
            overall=0.88,
            grade="B",
        )
        assert sc.overall == 0.88

    def test_release_decision_model_valid(self):
        rd = ReleaseDecision(
            case_id="test",
            decision="ready",
            summary="ok",
        )
        assert rd.decision == "ready"

    def test_scorecard_with_real_runtime(self):
        """Full pipeline: runtime passes → high score → release ready."""
        calc = ScorecardCalculator()
        gate = ReleaseGate()
        state = {
            "case_id": "regression-test",
            "runtime_validation_report": RuntimeValidationReport(
                case_id="regression-test",
                build_success=True,
                type_check_success=True,
                lint_success=True,
            ),
            "visual_regression_report": VisualRegressionReport(
                case_id="regression-test",
                reference_path="/ref.png",
                generated_path="/gen.png",
                ssim_score=0.98,
                pass_result=True,
            ),
            "normalization_report": None,
            "fix_attempts": [],
            "terminal_state": None,
            "retry_budget_remaining": 3,
        }
        sc = calc.calculate(state)
        assert sc.overall >= 0.85
        decision = gate.decide(state, sc)
        assert decision.decision == "ready"

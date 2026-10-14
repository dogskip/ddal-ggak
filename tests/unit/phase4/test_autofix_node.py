"""Tests for autofix_node — Wave 4 TDD (VALID-04)."""

from __future__ import annotations

from unittest.mock import MagicMock

from ddk.graph.nodes.autofix import autofix_node
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.services.failure_signature import failure_signature


def _make_artifacts(case_id: str = "tc") -> GeneratedArtifactSet:
    return GeneratedArtifactSet(case_id=case_id, files=[])


class FakeAutoFixPlanner:
    def __init__(self) -> None:
        self.visual_seen: list[object] = []

    async def plan_and_apply(self, failures, artifacts, case_id, attempt_number, visual=None):
        self.visual_seen.append(visual)
        attempt = FixAttempt(
            attempt_number=attempt_number,
            case_id=case_id,
            rule_id="R-01",
            patch_description="test",
            success=True,
        )
        return attempt, artifacts


class FakeRollbackController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def create_checkpoint(self, case_id: str, attempt_number: int) -> str:
        self.calls.append((case_id, attempt_number))
        return f"fake-ref:{case_id}:{attempt_number}"


class UnavailableRollbackController:
    async def create_checkpoint(self, case_id: str, attempt_number: int) -> str:
        raise ValueError("fatal: not a git repository")


def make_report_with_failure(file_path: str = "src/App.tsx") -> RuntimeValidationReport:
    f = FailureRecord(
        id="f1",
        taxonomy_id="FT-LINT-001",
        severity="minor",
        message="test",
        file_path=file_path,
    )
    return RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=True,
        lint_success=True,
        failures=[f],
    )


async def test_autofix_node_decrements_retry_budget() -> None:
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }
    result = await autofix_node(state, context=container)
    assert result["retry_budget_remaining"] == 1


async def test_autofix_node_appends_fix_attempt() -> None:
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }
    result = await autofix_node(state, context=container)
    assert len(result["fix_attempts"]) == 1


async def test_autofix_node_attaches_checkpoint_ref_when_controller_configured() -> None:
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    container.rollback_controller = FakeRollbackController()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }
    result = await autofix_node(state, context=container)
    assert result["fix_attempts"][0].checkpoint_ref == "fake-ref:tc:1"


async def test_autofix_node_appends_failure_hash_before_fix() -> None:
    """autofix_node must record current failure hash BEFORE applying fix.

    This enables route_after_validate to detect oscillation on the NEXT validate cycle:
    if the same failures recur (fix didn't work), cur_hash will already be in history.
    """
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    report = make_report_with_failure(file_path="src/App.tsx")
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": report,
        "failure_hash_history": [],
    }
    result = await autofix_node(state, context=container)
    assert "failure_hash_history" in result
    assert len(result["failure_hash_history"]) == 1
    # Signature must not depend on the per-run UUID
    assert result["failure_hash_history"][0] == failure_signature(report.failures)


async def test_autofix_node_none_artifacts_returns_manual_review() -> None:
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": None,
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }
    result = await autofix_node(state, context=container)
    assert result.get("terminal_state") == "manual-review-required"


class NoOpAutoFixPlanner:
    async def plan_and_apply(self, failures, artifacts, case_id, attempt_number, visual=None):
        attempt = FixAttempt(
            attempt_number=attempt_number,
            case_id=case_id,
            rule_id="none",
            patch_description="No patch applied: model returned the file unchanged",
            success=False,
        )
        return attempt, artifacts


async def test_autofix_node_hands_over_to_a_human_when_nothing_was_changed() -> None:
    """Re-validating unchanged code cannot help, so an empty attempt ends the loop."""
    container = MagicMock()
    container.auto_fix_planner = NoOpAutoFixPlanner()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }

    result = await autofix_node(state, context=container)

    assert result["terminal_state"] == "manual-review-required"
    assert "unchanged" in result["error_message"]
    assert result["retry_budget_remaining"] == 1
    assert len(result["fix_attempts"]) == 1


async def test_autofix_node_keeps_going_after_a_real_patch() -> None:
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }

    result = await autofix_node(state, context=container)

    assert "terminal_state" not in result


async def test_autofix_node_hands_the_visual_report_to_the_planner() -> None:
    planner = FakeAutoFixPlanner()
    container = MagicMock()
    container.auto_fix_planner = planner
    visual = object()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "visual_regression_report": visual,
        "failure_hash_history": [],
    }

    await autofix_node(state, context=container)

    assert planner.visual_seen == [visual]


async def test_autofix_node_carries_on_when_no_checkpoint_can_be_made() -> None:
    """A folder without git history must not stop the repair loop."""
    container = MagicMock()
    container.auto_fix_planner = FakeAutoFixPlanner()
    container.rollback_controller = UnavailableRollbackController()
    state = {
        "case_id": "tc",
        "fix_attempts": [],
        "retry_budget_remaining": 2,
        "generated_artifacts": _make_artifacts(),
        "runtime_validation_report": make_report_with_failure(),
        "failure_hash_history": [],
    }

    result = await autofix_node(state, context=container)

    assert "terminal_state" not in result
    assert result["fix_attempts"][0].checkpoint_ref is None

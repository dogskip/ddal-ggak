"""Tests for autofix_node — Wave 4 TDD (VALID-04)."""
from __future__ import annotations

from unittest.mock import MagicMock

from ddk.graph.nodes.autofix import autofix_node
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.validation import FailureRecord, RuntimeValidationReport


def _make_artifacts(case_id: str = "tc") -> GeneratedArtifactSet:
    return GeneratedArtifactSet(case_id=case_id, files=[])


class FakeAutoFixPlanner:
    async def plan_and_apply(self, failures, artifacts, case_id, attempt_number):
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
    # Hash must be based on (taxonomy_id, file_path), not UUID
    expected_hash = hash(
        frozenset((f.taxonomy_id, f.file_path or "") for f in report.failures)
    )
    assert result["failure_hash_history"][0] == expected_hash


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

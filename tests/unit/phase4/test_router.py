"""Tests for route_after_validate — Wave 4 TDD (VALID-04)."""

from __future__ import annotations

import uuid

from ddk.graph.router import route_after_validate
from ddk.models.validation import FailureRecord, RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport


def make_state(
    report=None,
    vis_report=None,
    budget: int = 3,
    hash_history=None,
    terminal_state=None,
):
    return {
        "runtime_validation_report": report,
        "visual_regression_report": vis_report,
        "retry_budget_remaining": budget,
        "failure_hash_history": hash_history or [],
        "terminal_state": terminal_state,
    }


def test_route_pass_when_no_reports() -> None:
    state = make_state()
    assert route_after_validate(state) == "pass"


def test_route_pass_when_all_checks_pass() -> None:
    report = RuntimeValidationReport(
        case_id="tc", build_success=True, type_check_success=True, lint_success=True
    )
    vis = VisualRegressionReport(
        case_id="tc",
        reference_path="r.png",
        generated_path="g.png",
        ssim_score=0.95,
        pass_result=True,
    )
    state = make_state(report=report, vis_report=vis)
    assert route_after_validate(state) == "pass"


def test_route_exhausted_when_budget_zero() -> None:
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=True,
        lint_success=True,
        failures=[
            FailureRecord(
                id="f1",
                taxonomy_id="FT-BUILD-001",
                severity="critical",
                message="err",
            )
        ],
    )
    state = make_state(report=report, budget=0)
    assert route_after_validate(state) == "exhausted"


def test_route_exhausted_when_manual_review_already_requested() -> None:
    state = make_state(terminal_state="manual-review-required", budget=3)
    assert route_after_validate(state) == "exhausted"


def test_route_fix_available_when_failures_and_budget() -> None:
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=True,
        lint_success=True,
        failures=[
            FailureRecord(
                id="f1",
                taxonomy_id="FT-BUILD-001",
                severity="critical",
                message="err",
                file_path="src/App.tsx",
            )
        ],
    )
    state = make_state(report=report, budget=2, hash_history=[])
    assert route_after_validate(state) == "fix_available"


def test_route_exhausted_on_oscillation() -> None:
    """CRITICAL: oscillation uses (taxonomy_id, file_path) hash, not UUID."""
    failures = [
        FailureRecord(
            id="NEW-UUID-1",
            taxonomy_id="FT-BUILD-001",
            severity="critical",
            message="err",
            file_path="src/App.tsx",
        )
    ]
    expected_hash = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in failures))
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=True,
        lint_success=True,
        failures=failures,
    )
    state = make_state(report=report, budget=2, hash_history=[expected_hash])
    assert route_after_validate(state) == "exhausted"


def test_route_hash_uses_taxonomy_id_not_uuid() -> None:
    """Two FailureRecords with SAME taxonomy+file but DIFFERENT UUIDs → same hash → oscillation."""
    f1 = FailureRecord(
        id=str(uuid.uuid4()),
        taxonomy_id="FT-TYPE-001",
        severity="major",
        message="err",
        file_path="src/Foo.tsx",
    )
    f2 = FailureRecord(
        id=str(uuid.uuid4()),
        taxonomy_id="FT-TYPE-001",
        severity="major",
        message="err",
        file_path="src/Foo.tsx",
    )
    h1 = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in [f1]))
    h2 = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in [f2]))
    assert h1 == h2, "Hash must be based on taxonomy_id+file_path, not UUID"
    report = RuntimeValidationReport(
        case_id="tc",
        build_success=False,
        type_check_success=True,
        lint_success=True,
        failures=[f2],
    )
    state = make_state(report=report, budget=2, hash_history=[h1])
    assert route_after_validate(state) == "exhausted"

from __future__ import annotations

import copy

import pytest
from scripts.check_reproducibility import summarize


def receipts():
    return [
        {
            "repository": repository,
            "runtime": runtime,
            "variant": variant,
            "decision": "ready" if variant == "ready" else "blocked",
            "replay_decision": "ready" if variant == "ready" else "blocked",
            "evidence_integrity": True,
            "source_preserved": True,
            "cleanup_complete": True,
            "model_calls": 0,
            "actual_cost_micro_usd": 0,
            "duration_s": 1.0,
        }
        for runtime in ("host", "isolated")
        for repository in ("python", "javascript", "browser")
        for variant in ("ready", "target-missed", "regression")
    ]


def test_complete_matrix_counts_expected_rejections_separately_from_failures():
    result = summarize(receipts(), pytest_exit=0, skipped=0)
    assert result["status"] == "passed"
    assert result["runs"] == 18
    assert result["ready"] == 6
    assert result["expected_blocked"] == 12
    assert result["model_calls"] == 0
    assert result["actual_cost_micro_usd"] == 0
    assert result["repair_success_rate"] is None


@pytest.mark.parametrize("change", ["missing", "duplicate", "unexpected", "unknown-cost"])
def test_incomplete_or_ambiguous_receipts_cannot_pass(change):
    rows = copy.deepcopy(receipts())
    if change == "missing":
        rows.pop()
    elif change == "duplicate":
        rows[-1] = rows[0]
    elif change == "unexpected":
        rows[0]["runtime"] = "remote"
    else:
        rows[0]["actual_cost_micro_usd"] = None
    assert summarize(rows, pytest_exit=0, skipped=0)["status"] == "failed"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "blocked"),
        ("replay_decision", "blocked"),
        ("evidence_integrity", False),
        ("source_preserved", False),
        ("cleanup_complete", False),
        ("model_calls", 1),
        ("duration_s", -1),
    ],
)
def test_zero_exit_does_not_override_failed_evidence(field, value):
    rows = receipts()
    rows[0][field] = value
    assert summarize(rows, pytest_exit=0, skipped=0)["status"] == "failed"


@pytest.mark.parametrize(("exit_code", "skipped"), [(1, 0), (0, 1)])
def test_process_failures_and_skips_are_not_matrix_success(exit_code, skipped):
    assert summarize(receipts(), pytest_exit=exit_code, skipped=skipped)["status"] == "failed"

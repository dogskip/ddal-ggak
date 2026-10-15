from __future__ import annotations

import json

import pytest

from ddk.services.repair_diagnostics import RepairStallTracker, error_signature
from tests.unit.test_verified_change_engine import scenario as scenario
from tests.unit.test_verified_repair import answer, repair, with_limits
from tests.unit.test_verified_repair import blocked as blocked


def failures(message="same assertion"):
    return (
        {
            "check_id": "target",
            "reason_code": "test_failed",
            "error_signature_sha256": error_signature(
                "target", "test_failed", (("log", message.encode()),)
            ),
        },
    )


def test_same_error_gets_one_strategy_change_then_halts_on_next_repeat():
    tracker = RepairStallTracker()
    assert tracker.observe(failures(), 0) is None
    first = tracker.observe(failures(), 1)
    assert first["streak_count"] == 2
    assert first["action_taken"] == "inject_anti_oscillation_constraint"
    second = tracker.observe(failures(), 2)
    assert second["streak_count"] == 3
    assert second["action_taken"] == "halt_repair_stalled"


def test_same_failure_count_with_new_errors_never_halts_as_identical_error():
    tracker = RepairStallTracker()
    assert tracker.observe(failures("first"), 0) is None
    for number in range(1, 5):
        result = tracker.observe(failures(str(number)), number)
        assert result["stall_category"] == "failed_count_non_decreasing"
        assert result["action_taken"] == "inject_anti_oscillation_constraint"


def test_signature_normalizes_owned_temp_prefix_but_preserves_source_line_and_message():
    a = error_signature(
        "t", "failed", (("log", b"/tmp/ddk-evaluate-abc/app/src/a.py:42: bad type"),)
    )
    b = error_signature(
        "t", "failed", (("log", b"/tmp/ddk-evaluate-xyz/app/src/a.py:42: bad type"),)
    )
    c = error_signature(
        "t", "failed", (("log", b"/tmp/ddk-evaluate-xyz/app/src/a.py:43: bad type"),)
    )
    assert a == b and a != c


@pytest.mark.parametrize("warnings", ["", ", 1 warning", ", 2 warnings"])
def test_runner_duration_changes_do_not_hide_identical_assertions(warnings):
    signatures = [
        error_signature(
            "pytest",
            "test_failed",
            (
                (
                    "log",
                    (
                        "FAILED tests/test_login.py::test_empty - AssertionError: banner\n"
                        f"1 failed{warnings} in {duration}s\n"
                    ).encode(),
                ),
            ),
        )
        for duration in ("0.12", "0.13", "0.14")
    ]
    assert len(set(signatures)) == 1
    changed = error_signature(
        "pytest",
        "test_failed",
        (
            (
                "log",
                b"FAILED tests/test_login.py::test_empty - AssertionError: timeout after 0.15s\n"
                b"1 failed in 0.14s\n",
            ),
        ),
    )
    assert changed != signatures[0]


async def test_changing_source_bytes_cannot_spend_more_calls_on_the_same_error(blocked):
    variant = await with_limits(blocked, max_fix_attempts=5, max_provider_requests=5)
    calls = []

    async def provider(request):
        calls.append(json.loads(request.prompt))
        return answer("wrong-" + str(len(calls)))

    result = await repair(variant, provider)
    assert result["decision"] == "blocked"
    assert result["actions"][-1]["code"] == "repair_stalled"
    assert len(calls) == 2
    assert calls[1]["round_context"]["stall_constraints"]
    assert [r["action_taken"] for r in result["stall_diagnoses"]] == [
        "inject_anti_oscillation_constraint",
        "halt_repair_stalled",
    ]

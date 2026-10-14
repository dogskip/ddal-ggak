from __future__ import annotations

import json
from dataclasses import replace

import pytest

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.verified_reports import command_report, normalize_report
from tests.unit.adapters.test_verified_evaluator import request_for


@pytest.mark.parametrize(
    ("adapter", "payload", "executed", "skipped"),
    [
        (
            "junit-xml",
            (
                '<testsuite tests="2" failures="0" errors="0" skipped="1">'
                "<testcase/><testcase><skipped/></testcase></testsuite>"
            ),
            1,
            1,
        ),
        (
            "pytest-json",
            json.dumps({"summary": {"total": 3, "passed": 2, "failed": 0, "skipped": 1}}),
            2,
            1,
        ),
        (
            "jest-json",
            json.dumps(
                {"numTotalTests": 3, "numPassedTests": 2, "numFailedTests": 0, "numPendingTests": 1}
            ),
            2,
            1,
        ),
        (
            "vitest-json",
            json.dumps(
                {"numTotalTests": 3, "numPassedTests": 2, "numFailedTests": 0, "numPendingTests": 1}
            ),
            2,
            1,
        ),
        (
            "playwright-json",
            json.dumps({"stats": {"expected": 2, "unexpected": 0, "flaky": 0, "skipped": 1}}),
            2,
            1,
        ),
    ],
)
def test_native_counts_are_normalized_without_implicitly_allowing_skips(
    adapter, payload, executed, skipped, tmp_path
):
    request = request_for(tmp_path)[0]
    check = {**request.checks[0], "kind": "test", "report_adapter": adapter}
    result = command_report(request, check, BuildResult(True, payload, "", 0))
    assert result["executed_count"] == executed
    assert result["skipped_count"] == skipped
    assert result["reason_code"] == "test_report_incomplete"
    result = command_report(
        request, {**check, "allow_skipped": True}, BuildResult(True, payload, "", 0)
    )
    assert result["status"] == "passed"


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        '{"numTotalTests":true}',
        '{"numTotalTests":-1}',
        '{"numTotalTests":0,"numFailedTests":0,"numPendingTests":0}',
    ],
)
def test_invalid_or_empty_report_never_passes(payload, tmp_path):
    request = request_for(tmp_path)[0]
    check = {
        **request.checks[0],
        "kind": "test",
        "report_adapter": "jest-json",
        "allow_skipped": True,
    }
    assert command_report(request, check, BuildResult(True, payload, "", 0))["status"] != "passed"


def test_junit_entities_are_rejected(tmp_path):
    request = request_for(tmp_path)[0]
    check = {**request.checks[0], "kind": "test", "report_adapter": "junit-xml"}
    assert (
        command_report(
            request, check, BuildResult(True, '<!DOCTYPE a [<!ENTITY e "x">]><testsuite/>', "", 0)
        )["status"]
        == "unavailable"
    )


async def test_junit_file_report_is_fresh_and_outside_original_source(tmp_path):
    from ddk.adapters.verified_evaluator import VerifiedEvaluator

    request, original, _ = request_for(
        tmp_path,
        kind="test",
        argv=[
            "python3",
            "-c",
            (
                "import pathlib,sys;pathlib.Path(sys.argv[1]).write_text("
                """'<testsuite tests="1"><testcase/></testsuite>')"""
            ),
            "{report}",
        ],
    )
    check = {**request.checks[0], "report_adapter": "junit-xml"}
    request = replace(request, checks=(check,))
    result = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert result.results[0]["status"] == "passed", result.results
    assert result.results[0]["executed_count"] == 1
    assert not (original / "report.xml").exists()


@pytest.mark.parametrize(
    "payload",
    [
        b'<testsuite tests="1" failures="1"><testcase name="ok"/></testsuite>',
        b'<testsuites tests="1"><testsuite tests="1" errors="1">'
        b'<testcase name="ok"/></testsuite></testsuites>',
        (
            '<!DOCTYPE a [<!ENTITY x "x">]><testsuite tests="1"><testcase name="&x;"/></testsuite>'
        ).encode("utf-16"),
    ],
)
def test_junit_rejects_inconsistent_summary_and_non_utf8_dtd(payload):
    with pytest.raises(ValueError):
        normalize_report(payload, "junit-xml")


async def test_real_pytest_junit_report_is_observed_and_normalized(tmp_path):
    import sys

    from ddk.adapters.verified_evaluator import VerifiedEvaluator
    from ddk.services.source_snapshot import SourceSnapshot, manifest_digest
    from tests.unit.test_verified_change_engine import fixed_file

    request = request_for(
        tmp_path,
        kind="test",
        argv=[sys.executable, "-m", "pytest", "-q", "--junitxml={report}", "test_actual.py"],
    )[0]
    files = (fixed_file("test_actual.py", b"def test_actual():\n    assert 2 + 2 == 4\n"),)
    source = SourceSnapshot(files, manifest_digest(files))
    request = replace(
        request,
        snapshot=source,
        input_tree_sha256=source.tree_sha256,
        checks=({**request.checks[0], "report_adapter": "junit-xml", "timeout_ms": 5000},),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == "passed", outcome.results
    assert outcome.results[0]["executed_count"] == 1

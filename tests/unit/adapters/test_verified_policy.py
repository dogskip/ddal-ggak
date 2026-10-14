from __future__ import annotations

from dataclasses import replace

from ddk.adapters.verified_policy import evaluate_policy
from ddk.models.verified_change import canonical_json
from ddk.services.source_snapshot import SourceSnapshot, manifest_digest
from tests.unit.adapters.test_verified_evaluator import request_for
from tests.unit.test_verified_change_engine import fixed_file


def test_policy_reports_exact_lines_and_masks_secret_values(tmp_path):
    request = request_for(tmp_path)[0]
    files = (
        fixed_file("src/app.js", b'const key="sk-secret-value-1234567890";\nconsole.log(key);\n'),
    )
    request = replace(
        request,
        baseline_snapshot=SourceSnapshot((), manifest_digest(())),
        snapshot=SourceSnapshot(files, manifest_digest(files)),
    )
    definition = canonical_json(
        {
            "forbidden_paths": ["src/private/*"],
            "forbid_secret_patterns": ["sk-[a-z0-9-]+"],
            "forbid_regex": ["console\\.log"],
            "max_changed_files": 1,
            "max_changed_lines": 10,
        }
    )
    result, artifact = evaluate_policy(request, {**request.checks[0], "kind": "policy"}, definition)
    assert result["status"] == "failed"
    assert b'"line":2' in artifact.content
    assert b"sk-secret-value" not in artifact.content


def test_invalid_regex_and_unreviewed_acceptance_are_unavailable(tmp_path):
    request = request_for(tmp_path)[0]
    for definition in ({"forbid_regex": ["["]}, {"review_required": True}):
        result, _ = evaluate_policy(
            request, {**request.checks[0], "kind": "policy"}, canonical_json(definition)
        )
        assert result["status"] == "unavailable"


def test_regex_repeated_quantifiers_are_rejected_before_execution(tmp_path):
    request = request_for(tmp_path)[0]
    result, _ = evaluate_policy(
        request,
        {**request.checks[0], "kind": "policy"},
        canonical_json({"forbid_regex": ["a{0,8192}a{0,8192}b"]}),
    )
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "policy_pattern_unsupported"


async def test_owned_policy_worker_enforces_deadline_and_returns_evidence(tmp_path):
    import time

    from ddk.adapters.verified_policy import evaluate_policy_owned

    request = request_for(tmp_path)[0]
    check = {**request.checks[0], "kind": "policy", "timeout_ms": 1}
    started = time.monotonic()
    result, artifact = await evaluate_policy_owned(request, check, b"{}")
    assert result["status"] == "unavailable" and result["reason_code"] == "policy_timeout"
    assert time.monotonic() - started < 3 and b"policy_timeout" in artifact.content
    result, _ = await evaluate_policy_owned(request, {**check, "timeout_ms": 5000}, b"{}")
    assert result["status"] == "passed"


async def test_owned_policy_accepts_binary_sources_and_large_sealed_text(tmp_path):
    from ddk.adapters.verified_policy import evaluate_policy_owned

    request = request_for(tmp_path)[0]
    files = (fixed_file("favicon.png", b"\x89PNG\x00\xff"), fixed_file("large.txt", b"x" * 1200000))
    source = SourceSnapshot(files, manifest_digest(files))
    request = replace(request, baseline_snapshot=source, snapshot=source)
    result, _ = await evaluate_policy_owned(
        request,
        {**request.checks[0], "kind": "policy", "timeout_ms": 5000},
        canonical_json({"max_changed_files": 0}),
    )
    assert result["status"] == "passed", result

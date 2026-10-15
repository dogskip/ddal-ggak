from __future__ import annotations

import hashlib
import json

import pytest

from ddk.services.context_compactor import compact_diagnostic


def test_short_raw_is_preserved_and_hashes_refer_to_actual_bytes():
    raw = b"AssertionError: expected banner\n"
    result = compact_diagnostic("log", raw)
    assert result.content == raw
    assert result.compressor_kind == "raw"
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.compacted_sha256 == hashlib.sha256(result.content).hexdigest()
    assert result.raw_bytes == result.compacted_bytes == len(raw)


def test_failure_at_end_of_long_success_log_survives_with_stack_context():
    raw = (
        "PASS helper\n" * 3000 + "Traceback (most recent call last):\n  File app.py, line 44\n"
        "AssertionError: missing error banner\nFAILED test_login\n1 failed, 3000 passed\n"
    ).encode()
    result = compact_diagnostic("trace", raw, max_bytes=2048)
    assert len(result.content) <= 2048
    assert b"AssertionError: missing error banner" in result.content
    assert b"app.py, line 44" in result.content and b"1 failed" in result.content
    assert result.truncated and result.compressor_kind == "log_frame_extract"


def test_redaction_precedes_bounded_utf8_extraction():
    raw = (
        "결과 확인\n" * 1000 + "Authorization: Bearer sk-" + "a" * 48 + "\nFAILED auth\n"
    ).encode()
    result = compact_diagnostic("log", raw, max_bytes=511)
    assert len(result.content) <= 511
    result.content.decode("utf-8", errors="strict")
    assert ("sk-" + "a" * 48).encode() not in result.content
    assert result.raw_sha256 == hashlib.sha256(raw).hexdigest()
    assert result == compact_diagnostic("log", raw, max_bytes=511)


def test_ax_diff_keeps_changed_node_and_its_parent():
    baseline = b'- main:\n  - form "Login":\n    - button "Send"\n'
    candidate = b'- main:\n  - form "Login":\n    - button "Submit"\n'
    result = compact_diagnostic("ax_snapshot", candidate, baseline_bytes=baseline)
    assert result.compressor_kind == "ax_tree_diff"
    assert b"Login" in result.content and b"Send" in result.content and b"Submit" in result.content
    assert result.compacted_bytes == len(result.content)


def test_json_diagnostic_prioritizes_violations_and_line_numbers():
    raw = json.dumps(
        {
            "passed": ["ok"] * 2000,
            "violations": [{"path": "src/app.py", "line": 42, "code": "forbidden_regex"}],
        }
    ).encode()
    result = compact_diagnostic("data", raw, max_bytes=512)
    assert b"src/app.py" in result.content and b"42" in result.content
    assert len(result.content) <= 512 and result.compressor_kind == "json_schema_crush"


def test_real_browser_visual_measurements_survive_long_step_history():
    raw = json.dumps(
        {
            "steps": ["ok"] * 2000,
            "errors": ["rgb_mismatch"],
            "visuals": [{"step_id": "login", "mismatch_ppm": 123456, "ssim": 0.72}],
        }
    ).encode()
    result = compact_diagnostic("data", raw)
    assert b"123456" in result.content and b"0.72" in result.content


@pytest.mark.parametrize("limit", [0, -1, True, 100000000])
def test_invalid_bounds_are_rejected(limit):
    with pytest.raises(ValueError):
        compact_diagnostic("log", b"raw", max_bytes=limit)

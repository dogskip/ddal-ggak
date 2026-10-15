"""Deterministic, bounded excerpts; original evidence remains independently retrievable."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from dataclasses import dataclass
from typing import cast

from ddk.models.verified_change import Record
from ddk.security.redact import redact_string

_FAILURE = re.compile(
    r"error|fail|exception|traceback|assert|violation|mismatch|\bline\s+\d+|^\s+File\s",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompactedDiagnostic:
    content: bytes
    compressor_kind: str
    raw_bytes: int
    compacted_bytes: int
    raw_sha256: str
    compacted_sha256: str
    truncated: bool


def _clip(text: str, limit: int) -> bytes:
    return text.encode()[:limit].decode("utf-8", errors="ignore").encode()


def _frames(text: str, limit: int) -> bytes:
    lines = text.splitlines(keepends=True)
    priorities = [i for i, line in enumerate(lines) if _FAILURE.search(line)]
    selected = set(range(max(0, len(lines) - 15), len(lines)))
    for index in priorities:
        selected.update(range(max(0, index - 15), min(len(lines), index + 16)))
    if not priorities:
        selected.update(range(min(15, len(lines))))

    def render(indices: set[int]) -> str:
        parts: list[str] = []
        previous = -1
        for index in sorted(indices):
            if index > previous + 1:
                parts.append(f"... [lines {previous + 2}-{index} omitted] ...\n")
            parts.append(lines[index])
            previous = index
        if previous + 1 < len(lines):
            parts.append(f"... [lines {previous + 2}-{len(lines)} omitted] ...\n")
        return "".join(parts)

    result = render(selected)
    if len(result.encode()) <= limit:
        return result.encode()
    # Preserve the first failure and the final summary before adding surrounding lines.
    chosen: set[int] = set()
    ordered = [*priorities[:1], *range(max(0, len(lines) - 8), len(lines)), *priorities]
    ordered += sorted(selected, key=lambda i: min((abs(i - p) for p in priorities[:32]), default=i))
    for index in dict.fromkeys(ordered):
        proposed = chosen | {index}
        if len(render(proposed).encode()) <= limit:
            chosen = proposed
    if chosen:
        return render(chosen).encode()
    anchor = priorities[0] if priorities else 0
    return _clip(lines[anchor] if lines else text, limit)


def _ax_text(text: str) -> str:
    try:
        value = json.loads(text)
    except ValueError:
        return text
    if isinstance(value, dict):
        snapshot = cast(Record, value).get("snapshot")
        if isinstance(snapshot, str):
            return snapshot
    return text


def _ax_diff(baseline: str, candidate: str) -> str:
    before, after = baseline.splitlines(), candidate.splitlines()
    if len(before) + len(after) > 4000:
        return candidate
    return "\n".join(difflib.unified_diff(before, after, "baseline AX", "candidate AX", n=15))


def _json_diagnostic(text: str) -> str:
    if len(text.encode()) > 2 * 1024**2:
        return text
    try:
        value = json.loads(text)
    except ValueError:
        return text
    if not isinstance(value, dict):
        return text
    mapping = cast(Record, value)
    preferred = {
        key: mapping[key]
        for key in (
            "errors",
            "violations",
            "failures",
            "reason_code",
            "path",
            "line",
            "mismatch_ppm",
            "ssim",
            "visuals",
            "failed_count",
            "message",
            "snapshot",
        )
        if key in value
    }
    return json.dumps(preferred or value, ensure_ascii=False, sort_keys=True, indent=2)


def compact_diagnostic(
    kind: str,
    raw_bytes: bytes,
    baseline_bytes: bytes | None = None,
    max_bytes: int = 4096,
) -> CompactedDiagnostic:
    if type(max_bytes) is not int or not 1 <= max_bytes <= 65536:
        raise ValueError("invalid_compaction_limit")
    text = redact_string(raw_bytes.decode("utf-8", errors="strict"))
    method = "raw"
    working = text
    if kind == "ax_snapshot" and baseline_bytes is not None:
        baseline = redact_string(baseline_bytes.decode("utf-8", errors="strict"))
        working = _ax_diff(_ax_text(baseline), _ax_text(text))
        method = "ax_tree_diff"
    elif kind == "data" and len(text.encode()) > max_bytes:
        working = _json_diagnostic(text)
        method = "json_schema_crush"
    if len(working.encode()) > max_bytes:
        content = _frames(working, max_bytes)
        if method == "raw":
            method = "log_frame_extract"
    else:
        content = working.encode()
    return CompactedDiagnostic(
        content,
        method,
        len(raw_bytes),
        len(content),
        hashlib.sha256(raw_bytes).hexdigest(),
        hashlib.sha256(content).hexdigest(),
        working != text or content != text.encode(),
    )

"""Bounded, redacted retrieval of result-linked diagnostic evidence only."""

from __future__ import annotations

import hashlib

from ddk.models.verified_change import Record
from ddk.security.file_access import read_regular
from ddk.security.redact import redact_string
from ddk.services.verified_change_store import VerifiedChangeStore


def read_evidence(
    store: VerifiedChangeStore,
    run_id: str,
    artifact_id: str,
    *,
    offset: int = 0,
    limit: int = 4096,
) -> Record:
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 16384:
        raise ValueError("invalid_evidence_range")
    run = store.status(run_id)
    observed = {key for result in run["results"] for key in result["artifact_ids"]}
    artifact = next((a for a in run["artifacts"] if a["artifact_id"] == artifact_id), None)
    if (
        artifact is None
        or artifact_id not in observed
        or artifact["kind"] not in {"log", "trace", "data", "ax_snapshot"}
        or artifact["path"].startswith(
            (
                "artifacts/prompts/",
                "artifacts/proposals/",
                "artifacts/usage/",
                "artifacts/prices/",
                "artifacts/source/",
            )
        )
    ):
        raise ValueError("evidence_not_diagnostic")
    raw = read_regular(store.path_for("run", run_id) / artifact["path"], artifact["size_bytes"])
    if len(raw) != artifact["size_bytes"] or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
        raise ValueError("stored_file_integrity")
    redacted = redact_string(raw.decode("utf-8", errors="strict")).encode()
    if offset > len(redacted):
        raise ValueError("invalid_evidence_range")
    try:
        redacted[:offset].decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise ValueError("invalid_evidence_boundary") from error
    content = redacted[offset : offset + limit].decode("utf-8", errors="ignore")
    size = len(content.encode())
    if not size and offset < len(redacted):
        raise ValueError("evidence_range_too_small")
    return {
        "run_id": run_id,
        "artifact_id": artifact_id,
        "raw_sha256": artifact["sha256"],
        "redacted_sha256": hashlib.sha256(redacted).hexdigest(),
        "total_bytes": len(redacted),
        "offset": offset,
        "next_offset": offset + size,
        "content": content,
        "has_more": offset + size < len(redacted),
        "execution_repeated": False,
    }

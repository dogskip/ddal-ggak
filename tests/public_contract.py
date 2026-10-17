"""Read canonical data while checking the new public response boundary."""

from __future__ import annotations

import json


def public_payload(text: str) -> dict:
    payload = json.loads(text)
    assert payload["schema_version"] == "ddk/2"
    assert set(payload) == {"schema_version", "command", "status", "data", "error", "actions"}
    assert isinstance(payload["command"], str)
    assert isinstance(payload["data"], dict)
    assert isinstance(payload["actions"], list)
    data = payload["data"]
    if payload["error"] is not None and set(data) <= {
        "run_id",
        "case_id",
        "apply_id",
        "source_run_id",
    }:
        return {**data, "error": payload["error"]}
    return data

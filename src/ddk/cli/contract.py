"""The public CLI and MCP response contract."""

from __future__ import annotations

from ddk.models.verified_change import Record

SCHEMA_VERSION = "ddk/2"
EXIT_CODES = {
    "success": 0,
    "blocked": 1,
    "usage": 2,
    "configuration": 3,
    "unavailable": 4,
    "integrity": 5,
    "interrupted": 130,
}


def envelope(
    command: str,
    data: Record,
    *,
    status: str = "ok",
    code: str | None = None,
    message: str = "",
    actions: list[str] | None = None,
) -> Record:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "data": data,
        "error": {"code": code, "message": message} if code else None,
        "actions": actions or [],
    }

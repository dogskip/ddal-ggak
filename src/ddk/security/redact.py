"""Secret and credential redaction utilities — INFRA-06 / SEC-01.

Provides pattern-based redaction for log output and error messages.
Called by RedactingProcessor in ddk.logging.setup.
"""

from __future__ import annotations

import re
from typing import Any

REDACT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"(sk-[a-zA-Z0-9]{20,})")),
    ("anthropic_key", re.compile(r"(sk-ant-[a-zA-Z0-9\-]{20,})")),
    ("google_key", re.compile(r"(AIza[a-zA-Z0-9\-_]{35})")),
    ("bearer_token", re.compile(r"(Bearer\s+[a-zA-Z0-9\-_.~+/]+=*)")),
    (
        "env_secret",
        re.compile(r"([A-Z_]{3,}_(?:KEY|TOKEN|SECRET|PASSWORD|PASS)=[^\s\"']+)"),
    ),
    (
        "private_key",
        re.compile(
            r"(-----BEGIN (?:RSA |EC )?PRIVATE KEY-----[\s\S]*?-----END)",
            re.DOTALL,
        ),
    ),
    (
        "jwt",
        re.compile(r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})"),
    ),
]

_PLACEHOLDER = "[REDACTED]"


def redact_string(text: str) -> str:
    """Replace all secret patterns in *text* with ``[REDACTED]``.

    Args:
        text: Raw string that may contain credentials.

    Returns:
        String with all matched patterns replaced.
    """
    for _name, pattern in REDACT_PATTERNS:
        text = pattern.sub(_PLACEHOLDER, text)
    return text


def redact_dict(
    data: dict[str, Any],
    *,
    max_depth: int = 10,
    _current_depth: int = 0,
) -> dict[str, Any]:
    """Recursively redact string values in a nested dict.

    Args:
        data: Dictionary to redact (not mutated in place).
        max_depth: Maximum recursion depth. Values deeper than this are left untouched.
        _current_depth: Internal recursion counter.

    Returns:
        New dictionary with secrets replaced.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        if _current_depth >= max_depth:
            result[key] = value
        elif isinstance(value, str):
            result[key] = redact_string(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(
                value,  # pyright: ignore
                max_depth=max_depth,
                _current_depth=_current_depth + 1,
            )
        elif isinstance(value, list):
            redacted_list: list[Any] = []
            for item in value:  # pyright: ignore
                if isinstance(item, str):
                    redacted_list.append(redact_string(item))
                else:
                    redacted_list.append(item)  # pyright: ignore
            result[key] = redacted_list
        else:
            result[key] = value
    return result

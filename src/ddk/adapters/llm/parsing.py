"""Robust parsing of JSON emitted by free-text LLM responses.

Models routinely wrap JSON in markdown fences (```json … ```) or surround it with
prose. A naive ``json.loads`` then fails and the caller silently discards a valid
generation. This module tolerates those shapes so good output is not thrown away.

``complete_structured`` (tool_use) already returns clean JSON; this is for the
free-text ``complete`` path.
"""

from __future__ import annotations

import json
from typing import Any

from ddk.exceptions import LLMResponseError


def strip_code_fences(text: str) -> str:
    """Remove a surrounding ```lang … ``` (or ``` … ```) markdown fence, if present."""
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    lines = lines[1:]  # drop the opening fence (``` or ```json)
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]  # drop the closing fence
    return "\n".join(lines).strip()


def _extract_first_json(text: str) -> str | None:
    """Return the first balanced ``{…}`` / ``[…]`` block, ignoring braces in strings."""
    start = next((i for i, ch in enumerate(text) if ch in "{["), None)
    if start is None:
        return None
    depth = 0
    in_str = False
    esc = False
    for j in range(start, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    return None


def parse_llm_json(text: str) -> Any:
    """Parse JSON from an LLM response, tolerating fences and surrounding prose.

    Raises:
        LLMResponseError: if no parsable JSON can be recovered.
    """
    candidate = strip_code_fences(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    extracted = _extract_first_json(candidate)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    preview = text.strip()[:120]
    raise LLMResponseError(f"could not parse JSON from LLM response (starts with: {preview!r})")

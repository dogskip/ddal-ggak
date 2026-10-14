"""Diagnostics parser — compiler/linter/bundler output → per-location diagnostics. VALID-05.

Pure logic: no I/O. Recognises tsc (plain + pretty), ESLint (stylish + json),
esbuild/Vite/Rollup build errors and Next.js build errors. Anything else yields
nothing so callers can fall back to the raw output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

Severity = Literal["error", "warning"]

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

_TSC_PLAIN = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s+(?P<sev>error|warning)\s+"
    r"(?P<code>TS\d+):\s+(?P<msg>.*)$"
)
_TSC_PRETTY = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+) - (?P<sev>error|warning) "
    r"(?P<code>TS\d+): (?P<msg>.*)$"
)
_ESBUILD = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): (?P<sev>ERROR|WARNING): (?P<msg>.*)$"
)
_ESLINT_DETAIL = re.compile(
    r"^\s+(?P<line>\d+):(?P<col>\d+)\s+(?P<sev>error|warning)\s+(?P<rest>\S.*?)\s*$"
)
_ESLINT_RULE = re.compile(r"^[@\w][\w@/.-]*$")
_BUILD_FILE = re.compile(r"^file:\s+(?P<file>.+?)(?::(?P<line>\d+):(?P<col>\d+))?\s*$")
_NEXT_LOCATION = re.compile(r"^\./(?P<file>[^\s:]+)(?::(?P<line>\d+):(?P<col>\d+))?\s*$")
_BUNDLER_PLUGIN_HEADER = re.compile(r"^\[[\w:.-]+\]\s")
_NEXT_MESSAGE_PREFIX = re.compile(r"^(?:Type error|Syntax error|Error):\s*")
_ESLINT_JSON_START = re.compile(r'\[\s*\{\s*"filePath"')


@dataclass(frozen=True)
class Diagnostic:
    """One located problem reported by a build, type-check or lint tool."""

    message: str
    file_path: str | None = None
    line: int | None = None
    column: int | None = None
    code: str | None = None
    severity: Severity = "error"


def strip_ansi(text: str) -> str:
    """Remove ANSI colour/control sequences."""
    return _ANSI.sub("", text)


def parse_diagnostics(output: str, *, root: Path | None = None) -> list[Diagnostic]:
    """Parse combined stdout/stderr into diagnostics; ``[]`` when nothing is recognised."""
    text = strip_ansi(output)
    from_json = _parse_eslint_json(text, root)
    if from_json is not None:
        return from_json
    return _parse_lines(text, root)


def _parse_lines(text: str, root: Path | None) -> list[Diagnostic]:
    found: list[Diagnostic] = []
    last_header = ""
    expect_build_message = False
    pending_build_message: str | None = None
    next_location: tuple[str, int | None, int | None] | None = None
    continuing = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continuing = False
            continue

        if next_location is not None and not raw_line[:1].isspace():
            file, ln, col = next_location
            next_location = None
            found.append(
                Diagnostic(
                    message=_NEXT_MESSAGE_PREFIX.sub("", stripped),
                    file_path=_relativize(file, root),
                    line=ln,
                    column=col,
                )
            )
            continuing = False
            continue

        tsc = _TSC_PLAIN.match(line) or _TSC_PRETTY.match(line)
        if tsc is not None:
            found.append(
                Diagnostic(
                    message=tsc["msg"].strip(),
                    file_path=_relativize(tsc["file"], root),
                    line=int(tsc["line"]),
                    column=int(tsc["col"]),
                    code=tsc["code"],
                    severity=_severity(tsc["sev"]),
                )
            )
            continuing = True
            expect_build_message = False
            continue

        esbuild = _ESBUILD.match(line)
        if esbuild is not None:
            found.append(
                Diagnostic(
                    message=esbuild["msg"].strip(),
                    file_path=_relativize(esbuild["file"], root),
                    line=int(esbuild["line"]),
                    column=int(esbuild["col"]),
                    severity=_severity(esbuild["sev"]),
                )
            )
            expect_build_message = False
            pending_build_message = None
            continuing = False
            continue

        detail = _ESLINT_DETAIL.match(line)
        if detail is not None and last_header:
            message, code = _split_eslint_rest(detail["rest"])
            found.append(
                Diagnostic(
                    message=message,
                    file_path=_relativize(last_header, root),
                    line=int(detail["line"]),
                    column=int(detail["col"]),
                    code=code,
                    severity=_severity(detail["sev"]),
                )
            )
            continuing = False
            continue

        if not raw_line[:1].isspace():
            last_header = stripped
            continuing = False

            if stripped == "error during build:":
                expect_build_message = True
                continue

            location = _NEXT_LOCATION.match(stripped)
            if location is not None:
                next_location = (
                    location["file"],
                    int(location["line"]) if location["line"] else None,
                    int(location["col"]) if location["col"] else None,
                )
                continue

            if expect_build_message:
                if _BUNDLER_PLUGIN_HEADER.match(stripped):
                    continue
                pending_build_message = stripped
                expect_build_message = False
                continue

            located = _BUILD_FILE.match(stripped)
            if located is not None and pending_build_message is not None:
                found.append(
                    Diagnostic(
                        message=pending_build_message,
                        file_path=_relativize(located["file"], root),
                        line=int(located["line"]) if located["line"] else None,
                        column=int(located["col"]) if located["col"] else None,
                    )
                )
                pending_build_message = None
            continue

        if continuing and found:
            previous = found[-1]
            found[-1] = Diagnostic(
                message=f"{previous.message} {stripped}",
                file_path=previous.file_path,
                line=previous.line,
                column=previous.column,
                code=previous.code,
                severity=previous.severity,
            )

    return found


def _split_eslint_rest(rest: str) -> tuple[str, str | None]:
    """ESLint stylish puts the rule id after a run of 2+ spaces."""
    parts = re.split(r"\s{2,}", rest)
    if len(parts) >= 2 and _ESLINT_RULE.match(parts[-1]):
        return " ".join(parts[:-1]).strip(), parts[-1]
    return rest.strip(), None


def _parse_eslint_json(text: str, root: Path | None) -> list[Diagnostic] | None:
    match = _ESLINT_JSON_START.search(text)
    if match is None:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[match.start() :])
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None

    found: list[Diagnostic] = []
    for entry in cast("list[Any]", payload):
        if not isinstance(entry, dict) or "filePath" not in entry:
            continue
        record = cast("dict[str, Any]", entry)
        file_path = _relativize(str(record["filePath"]), root)
        messages = record.get("messages")
        if not isinstance(messages, list):
            continue
        for item in cast("list[Any]", messages):
            if not isinstance(item, dict):
                continue
            message = cast("dict[str, Any]", item)
            line = message.get("line")
            column = message.get("column")
            rule = message.get("ruleId")
            found.append(
                Diagnostic(
                    message=str(message.get("message", "")).strip(),
                    file_path=file_path,
                    line=line if isinstance(line, int) else None,
                    column=column if isinstance(column, int) else None,
                    code=rule if isinstance(rule, str) else None,
                    severity="warning" if message.get("severity") == 1 else "error",
                )
            )
    return found


def _severity(label: str) -> Severity:
    return "warning" if label.lower() == "warning" else "error"


def _relativize(file: str, root: Path | None) -> str:
    """Return ``file`` relative to ``root`` using ``/``; leave outside paths as they are."""
    cleaned = file.strip().strip("\"'")
    if cleaned.startswith("file://"):
        cleaned = cleaned[len("file://") :]
    cleaned = cleaned.replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    if root is None or not cleaned.startswith("/"):
        return cleaned

    target = PurePosixPath(_without_private_prefix(cleaned))
    for base in _root_candidates(root):
        try:
            return target.relative_to(PurePosixPath(_without_private_prefix(base))).as_posix()
        except ValueError:
            continue
    return cleaned


def _root_candidates(root: Path) -> list[str]:
    candidates = [root.as_posix()]
    try:
        resolved = root.resolve().as_posix()
    except OSError:
        return candidates
    if resolved not in candidates:
        candidates.append(resolved)
    return candidates


def _without_private_prefix(path: str) -> str:
    """macOS temp dirs show up under both ``/var`` and ``/private/var``."""
    return path[len("/private") :] if path.startswith("/private/") else path

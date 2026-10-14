"""Plain-text file blocks: ``=== FILE: path ===`` followed by the whole file.

Model answers carry source code more reliably in blocks than inside JSON strings
(no escaping, and a cut-off answer still leaves the finished blocks intact).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

FILE_HEADER = re.compile(r"^=== FILE: (?P<path>.+?) ===[ \t]*$", re.MULTILINE)

_PROTECTED = re.compile(
    r"(^|/)(package(-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|\.npmrc|\.gitignore"
    r"|tsconfig[^/]*\.json|(vite|next|vitest|eslint)\.config\.[^/]+|\.eslintrc[^/]*)$"
)

Language = Literal["typescript", "javascript", "css", "html", "json", "other"]
_LANGUAGES: dict[str, Language] = {
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".css": "css",
    ".html": "html",
    ".json": "json",
}


def is_protected_path(path: str) -> bool:
    """Dependency manifests, lockfiles and tool configuration: never written by the model."""
    return _PROTECTED.search(path) is not None


def language_of(path: str) -> Language:
    return _LANGUAGES.get(Path(path).suffix.lower(), "other")


def strip_fence(text: str) -> str:
    """Remove one surrounding markdown code fence, if any."""
    lines = text.strip("\n").splitlines()
    if lines and lines[0].lstrip().startswith("```"):
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines) + "\n"
    return text


def parse_file_blocks(text: str) -> list[tuple[str, str]]:
    """``(path, content)`` for every ``=== FILE: path ===`` block, in order."""
    headers = list(FILE_HEADER.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        blocks.append((header["path"].strip(), strip_fence(text[header.end() : end].lstrip("\n"))))
    return blocks

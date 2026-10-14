"""ContextPackBuilder — deterministic context packaging (CODEGEN-03).

Deterministic selection rules:
- sort_key = (priority_rank, relation_rank, line_bucket, normalized_path)
- MAX_FILES=6, MAX_LINES=300
- P1~P5 priority hierarchy
- insufficient_context=True when no P1 files found
- context_pack_hash = SHA256[:16] of canonical manifest JSON
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ddk.models.context_pack import ContextChunk, ContextPack
from ddk.security.redact import redact_string
from ddk.security.repo_paths import read_source

MAX_FILES = 6
MAX_LINES = 300

_PRIORITY_RANK: dict[str, int] = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}

_BINARY_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".mp3",
        ".mp4",
        ".wav",
        ".avi",
        ".mov",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".7z",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".pyc",
        ".pyo",
    }
)

# P1: entry-point files
_P1_PATTERNS = frozenset(
    {
        "src/App.tsx",
        "src/App.jsx",
        "src/main.tsx",
        "src/main.jsx",
        "src/index.tsx",
        "src/index.jsx",
        "package.json",
    }
)

# P2: config files
_P2_PATTERNS = frozenset(
    {
        "tsconfig.json",
        "vite.config.ts",
        "vite.config.js",
        "next.config.js",
        "next.config.ts",
    }
)


@dataclass
class _Candidate:
    """Internal representation of a candidate file for context packing."""

    path: str
    priority: Literal["P1", "P2", "P3", "P4", "P5"]
    relation_rank: int  # exact=1, same-dir=2, shared=3
    content: str

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        """Deterministic sort key per 24-context-pack-determinism.md §3.2."""
        return (
            _PRIORITY_RANK[self.priority],
            self.relation_rank,
            math.ceil(self.line_count / 50),  # line_bucket
            self.path.replace("\\", "/").lower(),  # normalized_path
        )


class ContextPackBuilder:
    """Builds deterministic ContextPack with P1-P5 priority, MAX_FILES=6, MAX_LINES=300.

    No LLM calls — pure deterministic algorithm.
    """

    def build(
        self,
        target_files: list[str],
        repo_path: Path,
        node_name: str = "generate",
    ) -> ContextPack:
        """Build a deterministic context pack for the given target files.

        Args:
            target_files: Relative paths of files to be generated/modified.
            repo_path: Root of the repository to scan.
            node_name: Name of the generation node requesting context.

        Returns:
            Deterministic ContextPack respecting MAX_FILES=6, MAX_LINES=300.
        """
        candidates = self._gather_candidates(repo_path, target_files)
        candidates.sort(key=lambda c: c.sort_key)

        # Select up to MAX_FILES candidates
        selected = candidates[:MAX_FILES]

        # Drop lowest-priority candidates until within MAX_LINES budget
        while self._total_lines(selected) > MAX_LINES and selected:
            selected.pop()

        # Check for P1 presence — insufficient context if no P1 files found
        has_p1 = any(c.priority == "P1" for c in selected)
        insufficient = not has_p1

        # Build ContextChunk instances
        chunks = [
            ContextChunk(
                path=c.path,
                priority=c.priority,
                start_line=1,
                end_line=c.line_count,
                content=c.content,
                content_sha256=hashlib.sha256(c.content.encode()).hexdigest(),
            )
            for c in selected
        ]

        # Compute deterministic hash over canonical manifest
        pack_hash = self._compute_hash(node_name, target_files, chunks)

        missing_for: list[str] = target_files if insufficient else []

        return ContextPack(
            node_name=node_name,
            target_files=target_files,
            chunks=chunks,
            total_lines=sum(c.end_line - c.start_line + 1 for c in chunks),
            insufficient_context=insufficient,
            missing_context_for=missing_for,
            context_pack_hash=pack_hash,
        )

    def _gather_candidates(self, repo_path: Path, target_files: list[str]) -> list[_Candidate]:
        """Scan repo_path and collect candidate files with priority classification."""
        candidates: list[_Candidate] = []
        target_dirs = {str(Path(tf).parent) for tf in target_files}

        for file_path in sorted(repo_path.rglob("*")):
            if file_path.is_symlink() or not file_path.is_file():
                continue

            rel = file_path.relative_to(repo_path).as_posix()

            # Exclude binary files by extension
            if file_path.suffix.lower() in _BINARY_EXTENSIONS:
                continue

            # Read file content (skip unreadable files)
            try:
                content = read_source(repo_path, rel).decode("utf-8")
            except (ValueError, OSError):
                continue

            # SECURITY: scrub inline credentials before they reach the LLM (layer 2).
            content = redact_string(content)

            priority = self._classify_priority(rel, target_dirs)
            relation_rank = self._classify_relation(rel, target_files, target_dirs)

            candidates.append(
                _Candidate(
                    path=rel,
                    priority=priority,
                    relation_rank=relation_rank,
                    content=content,
                )
            )

        return candidates

    def _classify_priority(
        self, rel_path: str, target_dirs: set[str]
    ) -> Literal["P1", "P2", "P3", "P4", "P5"]:
        """Classify file into P1-P5 priority tier per 24-context-pack-determinism.md."""
        # P1: entry-point files
        if rel_path in _P1_PATTERNS:
            return "P1"

        # P2: config files
        if rel_path in _P2_PATTERNS:
            return "P2"
        # tsconfig.*.json variants
        if rel_path.startswith("tsconfig.") and rel_path.endswith(".json"):
            return "P2"

        # P3: source component/hook files in src/
        if rel_path.endswith((".tsx", ".jsx", ".ts", ".js")) and rel_path.startswith("src/"):
            parent = str(Path(rel_path).parent)
            # Sibling in same dir as a target → P2
            if parent in target_dirs:
                return "P2"
            return "P3"

        # P4: style files
        if rel_path.endswith((".css", ".scss", ".sass", ".module.css", ".module.scss")):
            return "P4"

        # P5: everything else (docs, other config)
        return "P5"

    def _classify_relation(
        self,
        rel_path: str,
        target_files: list[str],
        target_dirs: set[str],
    ) -> int:
        """Classify relationship of file to target files.

        Returns:
            1 — exact match (file is a target)
            2 — same directory as a target
            3 — shared/other
        """
        if rel_path in target_files:
            return 1
        parent = str(Path(rel_path).parent)
        if parent in target_dirs:
            return 2
        return 3

    def _total_lines(self, candidates: list[_Candidate]) -> int:
        return sum(c.line_count for c in candidates)

    def _compute_hash(
        self,
        node_name: str,
        target_files: list[str],
        chunks: list[ContextChunk],
    ) -> str:
        """Compute deterministic SHA256[:16] hash over canonical manifest JSON.

        Per 24-context-pack-determinism.md §6.2: hash covers node_name,
        target_files, and chunk manifest (path, priority, start_line, end_line,
        content_sha256). Real content text is NOT included — content_sha256 suffices.
        """
        manifest = {
            "node_name": node_name,
            "target_files": sorted(target_files),
            "chunks": [
                {
                    "path": c.path,
                    "priority": c.priority,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "content_sha256": c.content_sha256,
                }
                for c in chunks
            ],
        }
        canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

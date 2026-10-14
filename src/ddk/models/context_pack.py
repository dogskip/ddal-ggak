"""ContextPack and ContextChunk Pydantic models (CODEGEN-03)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class ContextChunk(DDKBaseModel):
    """A single chunk of context content from a source file."""

    path: str
    priority: Literal["P1", "P2", "P3", "P4", "P5"]
    start_line: int
    end_line: int
    content: str
    content_sha256: str


class ContextPack(DDKBaseModel):
    """Deterministic context pack built for a generation node (CODEGEN-03).

    MAX_FILES=6, MAX_LINES=300, P1-P5 priority ordering.
    """

    node_name: str
    target_files: list[str]
    chunks: list[ContextChunk]
    total_lines: int
    insufficient_context: bool = False
    missing_context_for: list[str] = Field(default_factory=list)
    context_pack_hash: str
    schema_version: str = "1.0"

"""Standards compliance domain models — clause-to-artifact coverage mapping.

This is a *new-target* capability (doc 28): GSD has no explicit standards matrix.
The discipline (doc 27 §메시징 원칙): "국제표준 준수는 clause mapping으로만 말한다."
So this models *coverage of mapped clauses*, never a certification claim — a clause
is ``mapped`` only when the declared artifacts resolve on disk, and genuine gaps
are reported as gaps.

Reuses ``EvidenceRef`` from the Proof Program so the evidence vocabulary is unified.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, computed_field

from ._base import DDKBaseModel
from .proof import EvidenceRef

ClauseStatus = Literal["mapped", "partial", "gap"]


def _empty_evidence_refs() -> list[EvidenceRef]:
    return []


class StandardClause(DDKBaseModel):
    """One normative requirement of a standard, mapped to expected artifacts."""

    standard: str  # e.g. "ISO/IEC/IEEE 42010:2022"
    clause: str  # e.g. "5.4 — Architecture viewpoints"
    title: str
    requirement: str
    artifacts: list[EvidenceRef] = Field(default_factory=_empty_evidence_refs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> ClauseStatus:
        """mapped iff every referenced artifact resolves; gap iff none do."""
        if not self.artifacts:
            return "gap"
        present = sum(1 for ref in self.artifacts if ref.exists)
        if present == 0:
            return "gap"
        if present == len(self.artifacts):
            return "mapped"
        return "partial"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def key(self) -> str:
        return f"{self.standard} §{self.clause}"


def _empty_standard_clauses() -> list[StandardClause]:
    return []


class ComplianceReport(DDKBaseModel):
    """Coverage of the mapped clause catalog against the live repo."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    clauses: list[StandardClause] = Field(default_factory=_empty_standard_clauses)
    summary: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return len(self.clauses)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mapped(self) -> int:
        return sum(1 for c in self.clauses if c.status == "mapped")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def partial(self) -> int:
        return sum(1 for c in self.clauses if c.status == "partial")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def gaps(self) -> int:
        return sum(1 for c in self.clauses if c.status == "gap")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def coverage(self) -> float:
        """Fraction of clauses whose declared artifacts fully resolve (0.0–1.0)."""
        if not self.clauses:
            return 0.0
        return round(self.mapped / len(self.clauses), 4)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def standards(self) -> list[str]:
        return sorted({c.standard for c in self.clauses})

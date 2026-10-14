"""Proof Program domain models — the executable form of the Claim Gate.

These models turn ``docs/design/27-identity-positioning.md`` (Claim Gate) and
``docs/design/28-gsd-superset-matrix.md`` (capability matrix) from prose into
machine-checkable evidence. The whole point is the *evidence-gated* posture:
a claim about GSD parity / superset / superiority is only ``allowed`` when the
required artifacts actually resolve on disk and the gate conditions hold.

See ``ddk.services.proof_ledger`` for the verifier and gate logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, computed_field

from ._base import DDKBaseModel

# GSD lineage classification of a capability family (doc 28 §상태 정의).
Classification = Literal["inherit", "elevate", "new"]
# Evidence-derived proof state of a family.
ProofState = Literal["pending", "partial", "mapped", "proved"]
# Claim taxonomy from doc 27 §Claim 종류.
ClaimType = Literal["identity", "parity", "superset", "superiority", "release", "standards"]
# What a piece of evidence is.
EvidenceKind = Literal["code", "test", "report", "artifact", "doc", "benchmark"]
# Maturity ladder from doc 27 §Maturity Ladder.
MaturityLevel = Literal["P-0", "P-1", "P-2", "P-3", "P-4"]


class EvidenceRef(DDKBaseModel):
    """A pointer to a single artifact that backs a claim.

    ``path`` is repo-relative. ``exists`` is populated by the verifier; it is
    never trusted from the matrix source itself.
    """

    kind: EvidenceKind
    path: str
    description: str = ""
    exists: bool = False
    resolution_error: str | None = None


def _empty_evidence_refs() -> list[EvidenceRef]:
    return []


class CapabilityFamily(DDKBaseModel):
    """One row of the GSD-superset matrix with its resolved evidence."""

    id: str
    name: str
    gsd_baseline: str
    ddk_target: str
    classification: Classification
    evidence: list[EvidenceRef] = Field(default_factory=_empty_evidence_refs)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def state(self) -> ProofState:
        """Filesystem evidence can prove mapping, not runtime behavior."""
        if not self.evidence:
            return "pending"
        present = sum(1 for ref in self.evidence if ref.exists)
        if present == 0:
            return "pending"
        if present == len(self.evidence):
            return "mapped"
        return "partial"


class ClaimGateResult(DDKBaseModel):
    """Verdict for a single claim — the heart of the anti-overclaim guarantee."""

    claim_type: ClaimType
    subject: str = ""  # family id for parity claims; "" for system-wide claims
    allowed: bool
    satisfied: list[str] = Field(default_factory=list)
    unmet: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=_empty_evidence_refs)


def _empty_capability_families() -> list[CapabilityFamily]:
    return []


def _empty_claim_results() -> list[ClaimGateResult]:
    return []


class ProofReport(DDKBaseModel):
    """The full evidence-gated picture: what ddalggak may truthfully claim."""

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    families: list[CapabilityFamily] = Field(default_factory=_empty_capability_families)
    claims: list[ClaimGateResult] = Field(default_factory=_empty_claim_results)
    maturity_level: MaturityLevel = "P-0"
    summary: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_families(self) -> int:
        return len(self.families)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def proved(self) -> int:
        return sum(1 for fam in self.families if fam.state == "proved")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mapped(self) -> int:
        return sum(1 for fam in self.families if fam.state == "mapped")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def partial(self) -> int:
        return sum(1 for fam in self.families if fam.state == "partial")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def pending(self) -> int:
        return sum(1 for fam in self.families if fam.state == "pending")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_claims(self) -> list[str]:
        """Claim types with at least one allowed verdict — for honest messaging."""
        return sorted({c.claim_type for c in self.claims if c.allowed})

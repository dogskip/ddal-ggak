"""Operator authority domain models — explicit human release/claim authority.

A *new-target* capability (doc 28, doc 32): GSD's operator model is *implicit*.
ddalggak makes it explicit and enforceable — scoped authority, segregation of
duties (no self-approval), and process-local approval records. This is the
human sign-off layer that sits on top of the evidence-gated Claim Gate: evidence
makes a claim *eligible*; an authorized operator makes it *approved*.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel

# What kind of decision an operator may approve.
AuthorityScope = Literal[
    "release",
    "parity-claim",
    "superset-claim",
    "superiority-claim",
    "standards-claim",
]
OperatorRole = Literal[
    "author",
    "reviewer",
    "release-manager",
    "compliance-officer",
    "principal-architect",
]


def _empty_authority_scopes() -> list[AuthorityScope]:
    return []


class Operator(DDKBaseModel):
    """A human authority with an explicit set of approval scopes."""

    id: str
    name: str
    role: OperatorRole
    scopes: list[AuthorityScope] = Field(default_factory=_empty_authority_scopes)


class AuthorityDecision(DDKBaseModel):
    """Whether an operator may approve a given subject under a scope."""

    subject: str
    scope: AuthorityScope
    operator_id: str
    authorized: bool
    reasons: list[str] = Field(default_factory=list)


class ApprovalRecord(DDKBaseModel):
    """A validated process-local entry for a granted/refused approval."""

    record_id: str
    subject: str
    scope: AuthorityScope
    operator_id: str
    decision: Literal["approved", "rejected"]
    rationale: str
    author_id: str | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

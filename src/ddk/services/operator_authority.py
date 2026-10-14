"""Operator Authority — release/claim sign-off with segregation of duties.

Enforces three governance invariants on top of the evidence-gated Claim Gate:

1. **Scope grant** — an operator may approve a scope only if it is in their grants.
2. **Segregation of duties** — an operator may not approve their own work
   (``operator.id == author_id`` is refused for every scope).
3. **Architect floor for superiority** — only a ``principal-architect`` may approve
   a ``superiority-claim``, mirroring doc 27's strict superiority gate.

Approvals are appended to a process-local ledger whose public accessor returns a copy.
This is not durable audit storage. ``record_approval`` refuses to mint an *approved*
record unless authority holds.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from ddk.models.operator import (
    ApprovalRecord,
    AuthorityDecision,
    AuthorityScope,
    Operator,
)


class UnauthorizedApprovalError(RuntimeError):
    """Raised when an operator attempts an approval they are not authorized for."""


class OperatorRegistry:
    """An explicit set of operators keyed by id."""

    def __init__(self, operators: Iterable[Operator] = ()) -> None:
        self._by_id: dict[str, Operator] = {op.id: op for op in operators}

    def add(self, operator: Operator) -> None:
        self._by_id[operator.id] = operator

    def get(self, operator_id: str) -> Operator | None:
        return self._by_id.get(operator_id)

    def __len__(self) -> int:
        return len(self._by_id)


class AuthorityController:
    """Decide and record approvals against an OperatorRegistry."""

    def __init__(self, registry: OperatorRegistry) -> None:
        self._registry = registry
        self._ledger: list[ApprovalRecord] = []

    def can_approve(
        self,
        operator_id: str,
        scope: AuthorityScope,
        subject: str,
        author_id: str | None = None,
    ) -> AuthorityDecision:
        reasons: list[str] = []
        operator = self._registry.get(operator_id)

        if operator is None:
            return AuthorityDecision(
                subject=subject,
                scope=scope,
                operator_id=operator_id,
                authorized=False,
                reasons=[f"unknown operator: {operator_id}"],
            )

        if scope in operator.scopes:
            reasons.append(f"scope granted: {scope}")
        else:
            reasons.append(f"scope not granted: {scope}")

        sod_ok = author_id is None or author_id != operator.id
        if sod_ok:
            reasons.append("segregation of duties satisfied")
        else:
            reasons.append("segregation of duties violated: cannot approve own work")

        architect_ok = scope != "superiority-claim" or operator.role == "principal-architect"
        if scope == "superiority-claim":
            reasons.append(
                "principal-architect floor satisfied"
                if architect_ok
                else "superiority-claim requires principal-architect"
            )

        authorized = (scope in operator.scopes) and sod_ok and architect_ok
        return AuthorityDecision(
            subject=subject,
            scope=scope,
            operator_id=operator_id,
            authorized=authorized,
            reasons=reasons,
        )

    def record_approval(
        self,
        operator_id: str,
        scope: AuthorityScope,
        subject: str,
        rationale: str,
        author_id: str | None = None,
    ) -> ApprovalRecord:
        """Append an *approved* record — refuses if authority does not hold."""
        decision = self.can_approve(operator_id, scope, subject, author_id)
        if not decision.authorized:
            raise UnauthorizedApprovalError(
                f"{operator_id} cannot approve {scope} for {subject}: {'; '.join(decision.reasons)}"
            )
        record = ApprovalRecord(
            record_id=f"appr-{len(self._ledger) + 1:04d}",
            subject=subject,
            scope=scope,
            operator_id=operator_id,
            decision="approved",
            rationale=rationale,
            author_id=author_id,
            recorded_at=datetime.now(UTC),
        )
        self._ledger.append(record)
        return record

    def record_rejection(
        self,
        operator_id: str,
        scope: AuthorityScope,
        subject: str,
        rationale: str,
        author_id: str | None = None,
    ) -> ApprovalRecord:
        """Append a *rejected* record. Any known operator may reject."""
        if self._registry.get(operator_id) is None:
            raise UnauthorizedApprovalError(f"unknown operator: {operator_id}")
        record = ApprovalRecord(
            record_id=f"appr-{len(self._ledger) + 1:04d}",
            subject=subject,
            scope=scope,
            operator_id=operator_id,
            decision="rejected",
            rationale=rationale,
            author_id=author_id,
        )
        self._ledger.append(record)
        return record

    def ledger(self) -> list[ApprovalRecord]:
        """Return a copy of the process-local append-only approval records."""
        return list(self._ledger)

    def approvals_for(self, subject: str) -> list[ApprovalRecord]:
        return [r for r in self._ledger if r.subject == subject and r.decision == "approved"]

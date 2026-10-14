"""Unit tests for the Operator Authority subsystem."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddk.models.operator import ApprovalRecord, Operator
from ddk.services.operator_authority import (
    AuthorityController,
    OperatorRegistry,
    UnauthorizedApprovalError,
)


def _registry() -> OperatorRegistry:
    return OperatorRegistry(
        [
            Operator(id="alice", name="Alice", role="reviewer", scopes=["parity-claim"]),
            Operator(
                id="bob",
                name="Bob",
                role="release-manager",
                scopes=["release", "superset-claim"],
            ),
            Operator(
                id="carol",
                name="Carol",
                role="principal-architect",
                scopes=["superiority-claim", "release"],
            ),
            Operator(id="dave", name="Dave", role="reviewer", scopes=["superiority-claim"]),
        ]
    )


class TestModels:
    def test_operator_defaults_empty_scopes(self) -> None:
        assert Operator(id="x", name="X", role="author").scopes == []

    def test_record_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalRecord(
                record_id="r",
                subject="s",
                scope="release",
                operator_id="o",
                decision="approved",
                rationale="ok",
                bogus=1,  # type: ignore[call-arg]
            )


class TestRegistry:
    def test_add_get_len(self) -> None:
        reg = OperatorRegistry()
        assert len(reg) == 0
        reg.add(Operator(id="x", name="X", role="author"))
        assert len(reg) == 1
        assert reg.get("x") is not None
        assert reg.get("missing") is None


class TestCanApprove:
    def test_authorized_when_scope_granted(self) -> None:
        ctrl = AuthorityController(_registry())
        assert ctrl.can_approve("alice", "parity-claim", "claim:parity/x").authorized is True

    def test_denied_when_scope_not_granted(self) -> None:
        ctrl = AuthorityController(_registry())
        assert ctrl.can_approve("alice", "release", "release:c1").authorized is False

    def test_denied_for_unknown_operator(self) -> None:
        ctrl = AuthorityController(_registry())
        decision = ctrl.can_approve("ghost", "release", "release:c1")
        assert decision.authorized is False
        assert any("unknown operator" in r for r in decision.reasons)

    def test_segregation_of_duties_blocks_self_approval(self) -> None:
        ctrl = AuthorityController(_registry())
        decision = ctrl.can_approve("bob", "release", "release:c1", author_id="bob")
        assert decision.authorized is False
        assert any("segregation of duties violated" in r for r in decision.reasons)

    def test_superiority_requires_principal_architect(self) -> None:
        ctrl = AuthorityController(_registry())
        # dave holds the scope but is only a reviewer → denied by architect floor.
        assert ctrl.can_approve("dave", "superiority-claim", "claim:sup").authorized is False
        # carol is principal-architect with the scope → allowed.
        assert ctrl.can_approve("carol", "superiority-claim", "claim:sup").authorized is True


class TestRecordApproval:
    def test_records_when_authorized(self) -> None:
        ctrl = AuthorityController(_registry())
        record = ctrl.record_approval("bob", "release", "release:c1", "looks good")
        assert record.decision == "approved"
        assert record.record_id == "appr-0001"
        assert ctrl.approvals_for("release:c1") == [record]

    def test_raises_when_unauthorized(self) -> None:
        ctrl = AuthorityController(_registry())
        with pytest.raises(UnauthorizedApprovalError):
            ctrl.record_approval("alice", "release", "release:c1", "nope")

    def test_raises_on_self_approval(self) -> None:
        ctrl = AuthorityController(_registry())
        with pytest.raises(UnauthorizedApprovalError):
            ctrl.record_approval("bob", "release", "release:c1", "self", author_id="bob")

    def test_ledger_is_append_only_and_increments(self) -> None:
        ctrl = AuthorityController(_registry())
        ctrl.record_approval("bob", "release", "release:c1", "ok")
        ctrl.record_approval("carol", "release", "release:c2", "ok")
        ledger = ctrl.ledger()
        assert [r.record_id for r in ledger] == ["appr-0001", "appr-0002"]

    def test_rejection_allowed_for_known_operator(self) -> None:
        ctrl = AuthorityController(_registry())
        record = ctrl.record_rejection("alice", "release", "release:c1", "blocking issue")
        assert record.decision == "rejected"
        assert ctrl.approvals_for("release:c1") == []  # rejections are not approvals

    def test_rejection_raises_for_unknown_operator(self) -> None:
        ctrl = AuthorityController(_registry())
        with pytest.raises(UnauthorizedApprovalError):
            ctrl.record_rejection("ghost", "release", "release:c1", "x")

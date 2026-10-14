"""Unit tests for Proof Program domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddk.models.proof import (
    CapabilityFamily,
    ClaimGateResult,
    EvidenceRef,
    ProofReport,
)


def _ref(path: str, *, exists: bool) -> EvidenceRef:
    return EvidenceRef(kind="code", path=path, exists=exists)


def _family(fam_id: str, refs: list[EvidenceRef]) -> CapabilityFamily:
    return CapabilityFamily(
        id=fam_id,
        name=fam_id,
        gsd_baseline="x",
        ddk_target="y",
        classification="elevate",
        evidence=refs,
    )


class TestEvidenceRef:
    def test_exists_defaults_false(self) -> None:
        assert EvidenceRef(kind="code", path="a.py").exists is False

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            EvidenceRef(kind="code", path="a.py", bogus=1)  # type: ignore[call-arg]


class TestCapabilityFamilyState:
    def test_no_evidence_is_pending(self) -> None:
        assert _family("f", []).state == "pending"

    def test_all_present_is_mapped(self) -> None:
        fam = _family("f", [_ref("a", exists=True), _ref("b", exists=True)])
        assert fam.state == "mapped"

    def test_some_present_is_partial(self) -> None:
        fam = _family("f", [_ref("a", exists=True), _ref("b", exists=False)])
        assert fam.state == "partial"

    def test_none_present_is_pending(self) -> None:
        fam = _family("f", [_ref("a", exists=False)])
        assert fam.state == "pending"

    def test_state_recomputes_after_assignment(self) -> None:
        fam = _family("f", [_ref("a", exists=False)])
        assert fam.state == "pending"
        fam.evidence[0].exists = True
        assert fam.state == "mapped"


class TestProofReportAggregates:
    def test_counts_and_allowed_claims(self) -> None:
        report = ProofReport(
            families=[
                _family("a", [_ref("x", exists=True)]),
                _family("b", [_ref("x", exists=True), _ref("y", exists=False)]),
                _family("c", []),
            ],
            claims=[
                ClaimGateResult(claim_type="identity", allowed=True),
                ClaimGateResult(claim_type="parity", subject="a", allowed=True),
                ClaimGateResult(claim_type="superiority", allowed=False),
            ],
        )
        assert report.total_families == 3
        assert report.proved == 0
        assert report.mapped == 1
        assert report.partial == 1
        assert report.pending == 1
        assert report.allowed_claims == ["identity", "parity"]

    def test_defaults_are_empty(self) -> None:
        report = ProofReport()
        assert report.total_families == 0
        assert report.allowed_claims == []
        assert report.maturity_level == "P-0"

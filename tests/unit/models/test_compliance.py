"""Unit tests for standards compliance domain models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddk.models.compliance import ComplianceReport, StandardClause
from ddk.models.proof import EvidenceRef


def _clause(artifacts: list[EvidenceRef]) -> StandardClause:
    return StandardClause(
        standard="ISO/IEC 25010:2023",
        clause="Security",
        title="t",
        requirement="r",
        artifacts=artifacts,
    )


def _ref(*, exists: bool) -> EvidenceRef:
    return EvidenceRef(kind="doc", path="x", exists=exists)


class TestStandardClauseStatus:
    def test_no_artifacts_is_gap(self) -> None:
        assert _clause([]).status == "gap"

    def test_all_present_is_mapped(self) -> None:
        assert _clause([_ref(exists=True), _ref(exists=True)]).status == "mapped"

    def test_some_present_is_partial(self) -> None:
        assert _clause([_ref(exists=True), _ref(exists=False)]).status == "partial"

    def test_none_present_is_gap(self) -> None:
        assert _clause([_ref(exists=False)]).status == "gap"

    def test_key_format(self) -> None:
        assert _clause([]).key == "ISO/IEC 25010:2023 §Security"

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            StandardClause(
                standard="s",
                clause="c",
                title="t",
                requirement="r",
                bogus=1,  # type: ignore[call-arg]
            )


class TestComplianceReport:
    def test_aggregates_and_coverage(self) -> None:
        report = ComplianceReport(
            clauses=[
                _clause([_ref(exists=True)]),  # mapped
                _clause([_ref(exists=True), _ref(exists=False)]),  # partial
                _clause([_ref(exists=False)]),  # gap
                _clause([]),  # gap
            ]
        )
        assert report.total == 4
        assert report.mapped == 1
        assert report.partial == 1
        assert report.gaps == 2
        assert report.coverage == 0.25
        assert report.standards == ["ISO/IEC 25010:2023"]

    def test_empty_report_zero_coverage(self) -> None:
        report = ComplianceReport()
        assert report.coverage == 0.0
        assert report.standards == []

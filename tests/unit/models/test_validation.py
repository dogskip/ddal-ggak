"""Tests for models/validation.py — FAILURE_TAXONOMY, FailureRecord, RuntimeValidationReport."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ddk.models.validation import (
    FAILURE_TAXONOMY,
    FailureRecord,
    RuntimeValidationReport,
)


class TestFailureTaxonomy:
    def test_taxonomy_has_19_codes(self) -> None:
        assert len(FAILURE_TAXONOMY) == 19

    def test_taxonomy_codes_have_prefix(self) -> None:
        for code in FAILURE_TAXONOMY:
            assert code.startswith("FT-"), f"Code {code} missing FT- prefix"

    def test_taxonomy_values_are_strings(self) -> None:
        for desc in FAILURE_TAXONOMY.values():
            assert isinstance(desc, str) and len(desc) > 0


class TestFailureRecord:
    def test_create_minimal(self) -> None:
        rec = FailureRecord(
            id="f1",
            taxonomy_id="FT-BUILD-001",
            severity="critical",
            message="Module not found",
        )
        assert rec.file_path is None
        assert rec.line_number is None
        assert rec.raw_output == ""
        assert rec.suggested_fix is None

    def test_create_full(self) -> None:
        rec = FailureRecord(
            id="f2",
            taxonomy_id="FT-TYPE-001",
            severity="major",
            message="Type mismatch",
            file_path="src/app.ts",
            line_number=42,
            raw_output="error TS2322",
            suggested_fix="change type to string",
        )
        assert rec.file_path == "src/app.ts"
        assert rec.line_number == 42

    def test_severity_restricted(self) -> None:
        with pytest.raises(ValidationError):
            FailureRecord(
                id="f3",
                taxonomy_id="FT-BUILD-001",
                severity="unknown",  # type: ignore[arg-type]
                message="bad",
            )


class TestRuntimeValidationReport:
    def test_create_minimal(self) -> None:
        report = RuntimeValidationReport(
            case_id="case-1",
            build_success=True,
            type_check_success=True,
            lint_success=True,
        )
        assert report.failures == []
        assert report.runtime_errors == []
        assert report.duration_ms == 0
        assert isinstance(report.created_at, datetime)

    def test_with_failures(self) -> None:
        failure = FailureRecord(
            id="f1",
            taxonomy_id="FT-BUILD-002",
            severity="critical",
            message="Syntax error",
        )
        report = RuntimeValidationReport(
            case_id="case-2",
            build_success=False,
            type_check_success=True,
            lint_success=True,
            failures=[failure],
        )
        assert len(report.failures) == 1
        assert report.build_success is False

    def test_negative_duration_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RuntimeValidationReport(
                case_id="c",
                build_success=True,
                type_check_success=True,
                lint_success=True,
                duration_ms=-1,
            )

    def test_serialization_roundtrip(self) -> None:
        report = RuntimeValidationReport(
            case_id="case-rt",
            build_success=True,
            type_check_success=False,
            lint_success=True,
            runtime_errors=["boom"],
        )
        data = report.model_dump()
        restored = RuntimeValidationReport.model_validate(data)
        assert restored.case_id == "case-rt"
        assert restored.runtime_errors == ["boom"]

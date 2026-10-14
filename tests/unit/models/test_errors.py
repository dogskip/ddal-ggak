"""Tests for models/errors.py — ErrorCategory, ErrorSeverity, DDKError, ErrorChain."""

from __future__ import annotations

from datetime import datetime

from ddk.models.errors import DDKError, ErrorCategory, ErrorChain, ErrorSeverity


class TestErrorCategory:
    def test_enum_values(self) -> None:
        assert ErrorCategory.LLM == "llm"
        assert ErrorCategory.BUILD == "build"
        assert ErrorCategory.UNKNOWN == "unknown"

    def test_all_categories_are_strings(self) -> None:
        for cat in ErrorCategory:
            assert isinstance(cat.value, str)


class TestErrorSeverity:
    def test_enum_values(self) -> None:
        assert ErrorSeverity.CRITICAL == "critical"
        assert ErrorSeverity.BLOCKER == "blocker"
        assert ErrorSeverity.MINOR == "minor"
        assert ErrorSeverity.INFO == "info"


class TestDDKError:
    def test_create_minimal(self) -> None:
        err = DDKError(
            code="E001",
            category=ErrorCategory.LLM,
            severity=ErrorSeverity.CRITICAL,
            message="LLM call failed",
        )
        assert err.code == "E001"
        assert err.node is None
        assert err.recoverable is True
        assert isinstance(err.timestamp, datetime)

    def test_create_full(self) -> None:
        err = DDKError(
            code="E002",
            category=ErrorCategory.BUILD,
            severity=ErrorSeverity.MAJOR,
            message="Build failed",
            node="validate",
            detail={"file": "index.ts"},
            recoverable=False,
        )
        assert err.node == "validate"
        assert err.detail == {"file": "index.ts"}
        assert err.recoverable is False

    def test_timestamp_is_utc(self) -> None:
        err = DDKError(
            code="E003",
            category=ErrorCategory.RUNTIME,
            severity=ErrorSeverity.MINOR,
            message="minor issue",
        )
        assert err.timestamp.tzinfo is not None


class TestErrorChain:
    def test_empty_chain(self) -> None:
        chain = ErrorChain(case_id="case-1")
        assert chain.errors == []
        assert chain.has_critical is False
        assert chain.has_blocker is False

    def test_has_critical_true(self) -> None:
        chain = ErrorChain(
            case_id="case-1",
            errors=[
                DDKError(
                    code="E001",
                    category=ErrorCategory.LLM,
                    severity=ErrorSeverity.CRITICAL,
                    message="critical",
                )
            ],
        )
        assert chain.has_critical is True
        assert chain.has_blocker is False

    def test_has_blocker_true(self) -> None:
        chain = ErrorChain(
            case_id="case-1",
            errors=[
                DDKError(
                    code="E002",
                    category=ErrorCategory.BUILD,
                    severity=ErrorSeverity.BLOCKER,
                    message="blocker",
                )
            ],
        )
        assert chain.has_blocker is True
        assert chain.has_critical is False

    def test_terminal_state(self) -> None:
        chain = ErrorChain(case_id="c1", terminal_state="manual-review-required")
        assert chain.terminal_state == "manual-review-required"

    def test_serialization_roundtrip(self) -> None:
        chain = ErrorChain(
            case_id="c1",
            errors=[
                DDKError(
                    code="E001",
                    category=ErrorCategory.LLM,
                    severity=ErrorSeverity.MINOR,
                    message="test",
                )
            ],
        )
        data = chain.model_dump()
        restored = ErrorChain.model_validate(data)
        assert restored.case_id == "c1"
        assert len(restored.errors) == 1

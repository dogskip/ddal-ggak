"""Unit tests for FailureClassifier — VALID-05.

TDD RED phase: tests written before implementation.
8 tests covering primary taxonomy paths + FT-UNKNOWN fallback.
"""

from __future__ import annotations

import pytest

from ddk.services.failure_classifier import FailureClassifier


@pytest.fixture()
def classifier() -> FailureClassifier:
    return FailureClassifier()


class TestFTUnknownFallback:
    def test_classify_unknown_returns_ft_unknown(self, classifier: FailureClassifier) -> None:
        """Completely unrecognized message must return FT-UNKNOWN, not a taxonomy ID."""
        result = classifier.classify("some completely gibberish xyz abc 12345")
        assert result.taxonomy_id == "FT-UNKNOWN"
        assert result.severity == "major"
        assert result.id != ""  # uuid4 must be set

    def test_classify_never_raises_on_empty_string(self, classifier: FailureClassifier) -> None:
        """Empty string must return FT-UNKNOWN, never raise."""
        result = classifier.classify("")
        assert result.taxonomy_id == "FT-UNKNOWN"

    def test_classify_passes_file_path_through(self, classifier: FailureClassifier) -> None:
        """file_path kwarg must appear in FailureRecord.file_path."""
        result = classifier.classify("gibberish", file_path="src/app.tsx")
        assert result.file_path == "src/app.tsx"


class TestBuildTaxonomy:
    def test_classify_module_not_found_returns_ft_build_001(
        self, classifier: FailureClassifier
    ) -> None:
        result = classifier.classify("Cannot find module './Button' or its type declarations")
        assert result.taxonomy_id == "FT-BUILD-001"
        assert result.severity == "critical"

    def test_classify_syntax_error_returns_ft_build_002(
        self, classifier: FailureClassifier
    ) -> None:
        result = classifier.classify("SyntaxError: Unexpected token '{'")
        assert result.taxonomy_id == "FT-BUILD-002"
        assert result.severity == "critical"


class TestTypeTaxonomy:
    def test_classify_type_mismatch_returns_ft_type_001(
        self, classifier: FailureClassifier
    ) -> None:
        result = classifier.classify("Argument of type 'number' is not assignable to type 'string'")
        assert result.taxonomy_id == "FT-TYPE-001"
        assert result.severity == "major"

    def test_classify_implicit_any_returns_ft_type_002(self, classifier: FailureClassifier) -> None:
        result = classifier.classify("Parameter 'event' implicitly has an 'any' type")
        assert result.taxonomy_id == "FT-TYPE-002"
        assert result.severity == "minor"


class TestLintTaxonomy:
    def test_classify_unused_var_returns_ft_lint_001(self, classifier: FailureClassifier) -> None:
        result = classifier.classify("Unused variable 'myVar' is defined but never used")
        assert result.taxonomy_id == "FT-LINT-001"
        assert result.severity == "minor"


class TestRuntimeTaxonomy:
    def test_classify_null_ref_returns_ft_runtime_002(self, classifier: FailureClassifier) -> None:
        result = classifier.classify(
            "Uncaught TypeError: Cannot read properties of null (reading 'value')"
        )
        assert result.taxonomy_id == "FT-RUNTIME-002"
        assert result.severity == "critical"

    def test_classify_unhandled_promise_returns_ft_runtime_001(
        self, classifier: FailureClassifier
    ) -> None:
        result = classifier.classify("UnhandledPromiseRejection: Error: fetch failed")
        assert result.taxonomy_id == "FT-RUNTIME-001"
        assert result.severity == "critical"


class TestResultProperties:
    def test_classify_result_has_unique_ids(self, classifier: FailureClassifier) -> None:
        """Each classify() call must produce a unique FailureRecord.id."""
        r1 = classifier.classify("Cannot find module './A'")
        r2 = classifier.classify("Cannot find module './A'")
        assert r1.id != r2.id

    @pytest.mark.parametrize(
        ("raw_message", "expected_tid"),
        [
            ("Cannot find module './X'", "FT-BUILD-001"),
            ("SyntaxError: Unexpected token", "FT-BUILD-002"),
            ("is not assignable to type 'string'", "FT-TYPE-001"),
            ("implicitly has an 'any' type", "FT-TYPE-002"),
            ("Unused variable 'x'", "FT-LINT-001"),
            ("Uncaught TypeError: Cannot read properties", "FT-RUNTIME-002"),
            ("Unhandled Promise rejection", "FT-RUNTIME-001"),
            ("404 Not Found", "FT-RUNTIME-003"),
            ("Layout shift detected", "FT-VISUAL-001"),
            ("await expression is not inside an async function", "FT-ASYNC-002"),
            ("completely unknown message xyz", "FT-UNKNOWN"),
        ],
    )
    def test_parametrize_taxonomy_coverage(
        self,
        classifier: FailureClassifier,
        raw_message: str,
        expected_tid: str,
    ) -> None:
        result = classifier.classify(raw_message)
        assert result.taxonomy_id == expected_tid, (
            f"Expected {expected_tid} for: {raw_message!r}, got {result.taxonomy_id}"
        )

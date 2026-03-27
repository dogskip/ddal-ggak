"""Tests for base models, config, and error hierarchy."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from ddk.models._base import DDKBaseModel
from ddk.models.errors import (
    DDKError,
    ErrorCategory,
    ErrorChain,
    ErrorSeverity,
)
from ddk.models.config import DdalggakConfig, LLMProvider


class TestDDKBaseModel:
    def test_rejects_extra_fields(self):
        class TestModel(DDKBaseModel):
            name: str

        with pytest.raises(Exception):  # ValidationError
            TestModel(name="test", unknown_field="bad")

    def test_validates_assignment(self):
        class TestModel(DDKBaseModel):
            count: int

        m = TestModel(count=5)
        with pytest.raises(Exception):
            m.count = "not_a_number"  # type: ignore


class TestErrorCategory:
    def test_enum_values(self):
        assert ErrorCategory.LLM == "llm"
        assert ErrorCategory.BUILD == "build"
        assert ErrorCategory.RUNTIME == "runtime"
        assert ErrorCategory.UNKNOWN == "unknown"

    def test_all_categories_exist(self):
        expected = {"llm", "build", "type_check", "lint", "runtime",
                    "visual", "data_binding", "async_timing", "unknown"}
        actual = {e.value for e in ErrorCategory}
        assert actual == expected


class TestErrorSeverity:
    def test_enum_values(self):
        assert ErrorSeverity.CRITICAL == "critical"
        assert ErrorSeverity.INFO == "info"

    def test_all_severities_exist(self):
        expected = {"critical", "blocker", "major", "minor", "info"}
        actual = {e.value for e in ErrorSeverity}
        assert actual == expected


class TestDDKError:
    def test_roundtrip(self):
        original = DDKError(
            code="ERR-001",
            category=ErrorCategory.BUILD,
            severity=ErrorSeverity.MAJOR,
            message="Build failed",
            node="generate",
            detail={"file": "App.tsx"},
            timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        json_str = original.model_dump_json()
        restored = DDKError.model_validate_json(json_str)
        assert original == restored

    def test_defaults(self):
        err = DDKError(
            code="ERR-002",
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.INFO,
            message="test",
        )
        assert err.node is None
        assert err.detail == {}
        assert err.recoverable is True


class TestErrorChain:
    def test_roundtrip(self):
        chain = ErrorChain(
            case_id="C-001",
            errors=[
                DDKError(
                    code="ERR-001",
                    category=ErrorCategory.BUILD,
                    severity=ErrorSeverity.CRITICAL,
                    message="Fatal",
                    timestamp=datetime(2025, 1, 1, tzinfo=timezone.utc),
                ),
            ],
            terminal_state="manual-review-required",
        )
        json_str = chain.model_dump_json()
        restored = ErrorChain.model_validate_json(json_str)
        assert restored.case_id == chain.case_id
        assert len(restored.errors) == 1
        assert restored.errors[0].code == "ERR-001"

    def test_has_critical(self):
        chain = ErrorChain(
            case_id="C-001",
            errors=[
                DDKError(
                    code="ERR-001",
                    category=ErrorCategory.BUILD,
                    severity=ErrorSeverity.CRITICAL,
                    message="Fatal",
                ),
            ],
        )
        assert chain.has_critical is True
        assert chain.has_blocker is False

    def test_empty_chain(self):
        chain = ErrorChain(case_id="C-001")
        assert chain.has_critical is False
        assert chain.has_blocker is False


class TestLLMProvider:
    def test_enum_values(self):
        assert LLMProvider.ANTHROPIC == "anthropic"
        assert LLMProvider.OPENAI == "openai"
        assert LLMProvider.FAKE == "fake"


class TestDdalggakConfig:
    def test_defaults(self):
        config = DdalggakConfig()
        assert config.llm_provider == LLMProvider.ANTHROPIC
        assert config.cost_cap_usd == 2.0
        assert config.max_retry_attempts == 3
        assert config.log_level == "INFO"

    def test_env_prefix(self, monkeypatch):
        monkeypatch.setenv("DDK_LLM_PROVIDER", "openai")
        monkeypatch.setenv("DDK_COST_CAP_USD", "5.0")
        config = DdalggakConfig()
        assert config.llm_provider == LLMProvider.OPENAI
        assert config.cost_cap_usd == 5.0

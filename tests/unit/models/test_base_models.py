"""Tests for base models, config, and error hierarchy."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddk.models._base import DDKBaseModel
from ddk.models.config import DdalggakConfig, LLMProvider


class TestDDKBaseModel:
    def test_rejects_extra_fields(self):
        class TestModel(DDKBaseModel):
            name: str

        with pytest.raises(ValidationError):
            TestModel(name="test", unknown_field="bad")

    def test_validates_assignment(self):
        class TestModel(DDKBaseModel):
            count: int

        m = TestModel(count=5)
        with pytest.raises(ValidationError):
            m.count = "not_a_number"  # type: ignore


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

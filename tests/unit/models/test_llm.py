"""Tests for models/llm.py — LLMCallRecord."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ddk.models.llm import LLMCallRecord


class TestLLMCallRecord:
    def test_create_minimal(self) -> None:
        rec = LLMCallRecord(
            call_id="call-1",
            case_id="case-1",
            node="generate",
            provider="anthropic",
            model="claude-3-5-sonnet-20241022",
        )
        assert rec.temperature == 0.0
        assert rec.input_tokens == 0
        assert rec.cost_usd == 0.0
        assert rec.success is True
        assert rec.error_message is None
        assert rec.schema_version == "1.0"

    def test_create_full(self) -> None:
        rec = LLMCallRecord(
            call_id="call-2",
            case_id="case-2",
            node="design_system",
            provider="openai",
            model="gpt-4o",
            temperature=0.7,
            seed=42,
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.05,
            success=False,
            error_message="rate limited",
        )
        assert rec.seed == 42
        assert rec.success is False
        assert rec.error_message == "rate limited"

    def test_temperature_bounds(self) -> None:
        with pytest.raises(ValidationError):
            LLMCallRecord(
                call_id="c",
                case_id="c",
                node="n",
                provider="p",
                model="m",
                temperature=2.5,
            )

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMCallRecord(
                call_id="c",
                case_id="c",
                node="n",
                provider="p",
                model="m",
                input_tokens=-1,
            )

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMCallRecord(
                call_id="c",
                case_id="c",
                node="n",
                provider="p",
                model="m",
                cost_usd=-0.01,
            )

    def test_timestamp_auto_generated(self) -> None:
        rec = LLMCallRecord(
            call_id="c",
            case_id="c",
            node="n",
            provider="p",
            model="m",
        )
        assert isinstance(rec.request_timestamp, datetime)

    def test_serialization_roundtrip(self) -> None:
        rec = LLMCallRecord(
            call_id="call-rt",
            case_id="case-rt",
            node="intake",
            provider="fake",
            model="fake-model",
        )
        data = rec.model_dump()
        restored = LLMCallRecord.model_validate(data)
        assert restored.call_id == "call-rt"

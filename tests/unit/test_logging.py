"""Unit tests for RedactingProcessor and redact_string / redact_dict utilities."""

from __future__ import annotations

from ddk.security.redact import redact_dict, redact_string


class TestRedactString:
    def test_openai_key_redacted(self) -> None:
        result = redact_string("key=sk-abc123defg456hijklmnop")
        assert "sk-" not in result
        assert "[REDACTED]" in result

    def test_anthropic_key_redacted(self) -> None:
        result = redact_string("Authorization: sk-ant-someloooongkey1234567890xyz")
        assert "sk-ant-" not in result
        assert "[REDACTED]" in result

    def test_google_key_redacted(self) -> None:
        result = redact_string("AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        assert "AIza" not in result
        assert "[REDACTED]" in result

    def test_bearer_token_redacted(self) -> None:
        result = redact_string("Authorization: Bearer eyABCDEF1234567890abcdef")
        assert "Bearer eyABCDEF" not in result
        assert "[REDACTED]" in result

    def test_env_secret_redacted(self) -> None:
        result = redact_string("DDK_ANTHROPIC_API_KEY=sk-ant-secret-value")
        assert "[REDACTED]" in result

    def test_jwt_redacted(self) -> None:
        jwt = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
            ".eyJzdWIiOiIxMjM0NTY3ODkwIn0"
            ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        )
        result = redact_string(jwt)
        assert "eyJhbGci" not in result
        assert "[REDACTED]" in result

    def test_plain_text_unchanged(self) -> None:
        text = "Hello, this is a safe message with no secrets."
        assert redact_string(text) == text

    def test_empty_string(self) -> None:
        assert redact_string("") == ""


class TestRedactDict:
    def test_flat_dict_string_values_redacted(self) -> None:
        data = {"key": "sk-ant-abc123abc123abc123abc123", "safe": "hello"}
        result = redact_dict(data)
        assert result["key"] == "[REDACTED]"
        assert result["safe"] == "hello"

    def test_nested_dict_redacted(self) -> None:
        data = {"outer": {"inner": "sk-ant-abc123abc123abc123abc123"}}
        result = redact_dict(data)
        assert result["outer"]["inner"] == "[REDACTED]"

    def test_list_values_redacted(self) -> None:
        data = {"tokens": ["sk-abc123defg456hijklmnop", "safe-value"]}
        result = redact_dict(data)
        assert "[REDACTED]" in result["tokens"]
        assert "safe-value" in result["tokens"]

    def test_non_string_values_unchanged(self) -> None:
        data = {"count": 42, "flag": True, "ratio": 3.14}
        result = redact_dict(data)
        assert result == data

    def test_original_not_mutated(self) -> None:
        data = {"key": "sk-ant-abc123abc123abc123abc123"}
        original_value = data["key"]
        redact_dict(data)
        assert data["key"] == original_value

    def test_max_depth_respected(self) -> None:
        # Build a deeply nested dict exceeding max_depth
        deep: dict = {}
        current = deep
        for _ in range(15):
            child: dict = {}
            current["child"] = child
            current = child
        current["secret"] = "sk-ant-abc123abc123abc123abc123"

        result = redact_dict(deep, max_depth=3)
        # Deep secret survives because depth > max_depth
        assert isinstance(result, dict)

    def test_empty_dict(self) -> None:
        assert redact_dict({}) == {}


class TestRedactingProcessor:
    def test_processor_redacts_event_dict(self) -> None:
        from ddk.logging.setup import RedactingProcessor

        processor = RedactingProcessor()
        event_dict = {"event": "api call", "key": "sk-ant-abc123abc123abc123abc123"}
        result = processor(None, "info", event_dict)
        assert result["key"] == "[REDACTED]"
        assert result["event"] == "api call"

    def test_processor_returns_new_dict(self) -> None:
        from ddk.logging.setup import RedactingProcessor

        processor = RedactingProcessor()
        event_dict = {"event": "test", "value": "safe"}
        result = processor(None, "info", event_dict)
        assert result is not event_dict

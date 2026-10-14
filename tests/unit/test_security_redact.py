"""Tests for security/redact.py — REDACT_PATTERNS, redact_string, redact_dict."""

from __future__ import annotations

from ddk.security.redact import REDACT_PATTERNS, redact_dict, redact_string


class TestRedactPatterns:
    def test_has_expected_patterns(self) -> None:
        names = {name for name, _pat in REDACT_PATTERNS}
        assert "openai_key" in names
        assert "anthropic_key" in names
        assert "bearer_token" in names
        assert "private_key" in names

    def test_all_patterns_have_compiled_regex(self) -> None:
        import re

        for name, pattern in REDACT_PATTERNS:
            assert isinstance(name, str)
            assert isinstance(pattern, re.Pattern)


class TestRedactString:
    def test_redacts_openai_key(self) -> None:
        text = "my key is sk-abc123def456ghi789jkl012mno345pqr678"
        result = redact_string(text)
        assert "[REDACTED]" in result

    def test_redacts_anthropic_key(self) -> None:
        text = "key=sk-ant-api03abcdef1234567890abc"
        result = redact_string(text)
        assert "[REDACTED]" in result

    def test_redacts_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test.sig"
        result = redact_string(text)
        assert "[REDACTED]" in result

    def test_redacts_private_key(self) -> None:
        text = "-----BEGIN RSA PRIVATE KEY-----\nMIIBogIBAAJ\n-----END RSA PRIVATE KEY-----"
        result = redact_string(text)
        assert "[REDACTED]" in result

    def test_no_secrets_returns_unchanged(self) -> None:
        text = "This is a normal log message with no secrets"
        assert redact_string(text) == text

    def test_multiple_secrets_all_redacted(self) -> None:
        text = "key1=sk-abc123def456ghi789jkl012 key2=sk-ant-api03xyz789abcdef12345678"
        result = redact_string(text)
        assert result.count("[REDACTED]") >= 2

    def test_empty_string(self) -> None:
        assert redact_string("") == ""


class TestRedactDict:
    def test_redacts_values(self) -> None:
        data = {"api_key": "sk-abc123def456ghi789jkl012mno345pqr678"}
        result = redact_dict(data)
        assert "[REDACTED]" in str(result["api_key"])

    def test_nested_dict(self) -> None:
        data = {"config": {"key": "sk-ant-api03secretvalue1234567890abc"}}
        result = redact_dict(data)
        inner = result["config"]["key"]
        assert "[REDACTED]" in str(inner)

    def test_preserves_non_secret_values(self) -> None:
        data = {"name": "test", "count": 42}
        result = redact_dict(data)
        assert result["name"] == "test"
        assert result["count"] == 42

    def test_empty_dict(self) -> None:
        assert redact_dict({}) == {}

    def test_list_values(self) -> None:
        data = {"keys": ["sk-abc123def456ghi789jkl012", "normal"]}
        result = redact_dict(data)
        assert isinstance(result["keys"], list)

    def test_max_depth_protection(self) -> None:
        deep: dict = {"level": {}}
        current = deep["level"]
        for _ in range(50):
            current["next"] = {}
            current = current["next"]
        current["secret"] = "sk-abc123def456ghi789jkl012mno345"
        result = redact_dict(deep, max_depth=5)
        assert isinstance(result, dict)

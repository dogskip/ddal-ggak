"""Tests for DdalggakConfig — validates AliasChoices env-var fallback behaviour."""
from __future__ import annotations

import pytest

from ddk.models.config import DdalggakConfig


class TestApiKeyAliasChoices:
    """Verify that both DDK_* prefix and plain env var names are accepted."""

    def test_ddk_prefix_sets_anthropic_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-ddk")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = DdalggakConfig()
        assert cfg.anthropic_api_key == "sk-ant-ddk"

    def test_bare_name_sets_anthropic_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ANTHROPIC_API_KEY (no prefix) is accepted as fallback."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bare")
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        cfg = DdalggakConfig()
        assert cfg.anthropic_api_key == "sk-ant-bare"

    def test_ddk_prefix_wins_over_bare_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When both are set, DDK_ANTHROPIC_API_KEY takes priority."""
        monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-ddk")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-bare")
        cfg = DdalggakConfig()
        assert cfg.anthropic_api_key == "sk-ant-ddk"

    def test_no_key_gives_empty_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        cfg = DdalggakConfig()
        assert cfg.anthropic_api_key == ""

    def test_ddk_prefix_sets_openai_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_OPENAI_API_KEY", "sk-openai-ddk")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        cfg = DdalggakConfig()
        assert cfg.openai_api_key == "sk-openai-ddk"

    def test_bare_name_sets_openai_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-bare")
        monkeypatch.delenv("DDK_OPENAI_API_KEY", raising=False)
        cfg = DdalggakConfig()
        assert cfg.openai_api_key == "sk-openai-bare"

    def test_ddk_openai_wins_over_bare(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_OPENAI_API_KEY", "sk-openai-ddk")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-bare")
        cfg = DdalggakConfig()
        assert cfg.openai_api_key == "sk-openai-ddk"

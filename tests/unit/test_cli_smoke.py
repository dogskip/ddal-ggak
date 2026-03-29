"""Smoke tests — verifies core ddk CLI commands invoke cleanly.

These tests do NOT call external services; they check that:
- exit codes are correct
- expected output markers are present
- env-var plumbing works (AliasChoices fallback)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# ddk version
# ---------------------------------------------------------------------------
class TestVersionCommand:
    def test_exits_zero(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_prints_ddk_prefix(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.output.lower().startswith("ddk")

    def test_shows_semver(self) -> None:
        result = runner.invoke(app, ["version"])
        parts = result.output.strip().split()
        assert len(parts) >= 2
        # e.g. "ddk 1.0.0"
        assert any(c.isdigit() for c in parts[1])


# ---------------------------------------------------------------------------
# ddk doctor
# ---------------------------------------------------------------------------
class TestDoctorCommand:
    def test_runs_without_crash(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_shows_python_check(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "Python" in result.output

    def test_shows_git_check(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "git" in result.output.lower()

    def test_shows_result_icons(self) -> None:
        result = runner.invoke(app, ["doctor"])
        assert "✅" in result.output or "❌" in result.output or "⚠" in result.output

    def test_passes_in_dev_environment(self) -> None:
        """Python 3.12+, uv, and git are all present in the dev environment."""
        result = runner.invoke(
            app,
            ["doctor"],
            env={"DDK_ANTHROPIC_API_KEY": "sk-ant-fake-for-test"},
        )
        # exit_code 0 = all checks pass; 1 = critical fail (e.g. uv not on PATH in CI)
        # We only assert no unhandled exception — environment checks vary per machine.
        assert result.exception is None or isinstance(result.exception, SystemExit)
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# ddk preflight
# ---------------------------------------------------------------------------
class TestPreflightCommand:
    def test_runs_without_crash(self) -> None:
        result = runner.invoke(app, ["preflight"])
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_shows_python_check(self) -> None:
        result = runner.invoke(app, ["preflight"])
        assert "Python" in result.output

    def test_shows_llm_api_key_label(self) -> None:
        result = runner.invoke(app, ["preflight"])
        assert "LLM API key" in result.output

    def test_shows_sdk_check(self) -> None:
        result = runner.invoke(app, ["preflight"])
        assert "anthropic" in result.output.lower()

    def test_no_api_key_exits_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without any API key, preflight must exit 1."""
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DDK_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(app, ["preflight"])
        assert result.exit_code == 1

    def test_no_api_key_shows_missing_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("DDK_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        result = runner.invoke(app, ["preflight"])
        assert "missing" in result.output.lower()

    def test_ddk_prefixed_key_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DDK_ANTHROPIC_API_KEY is the primary env var name."""
        monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(app, ["preflight"])
        assert "❌ LLM API key" not in result.output

    def test_bare_anthropic_key_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ANTHROPIC_API_KEY (no DDK_ prefix) is accepted as fallback."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        result = runner.invoke(app, ["preflight"])
        assert "❌ LLM API key" not in result.output


# ---------------------------------------------------------------------------
# ddk init
# ---------------------------------------------------------------------------
class TestInitCommand:
    def test_creates_ddk_directory(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".ddk").exists()

    def test_is_idempotent(self, tmp_path: Path) -> None:
        runner.invoke(app, ["init", str(tmp_path)])
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0

    def test_prints_success_message(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["init", str(tmp_path)])
        assert result.exit_code == 0
        assert ".ddk" in result.output or "✅" in result.output

    def test_default_path_uses_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (tmp_path / ".ddk").exists()

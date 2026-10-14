"""PreflightDoctor provider/key contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.adapters.chromium_browser import (
    PLAYWRIGHT_BUILD,
    BrowserUnavailableError,
    ChromiumBrowserAdapter,
)
from ddk.models.config import DdalggakConfig
from ddk.preflight.doctor import PreflightDoctor


def _probe(monkeypatch: pytest.MonkeyPatch, outcome: str | Exception) -> None:
    """Make the browser start-up test end the way ``outcome`` says, without a real browser."""

    async def fake(self: ChromiumBrowserAdapter) -> str:
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(ChromiumBrowserAdapter, "probe", fake)


def test_unsupported_provider_key_does_not_satisfy_runtime_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-reserved")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-reserved")

    result = PreflightDoctor()._check_api_key()

    assert result["status"] == "fail"


class TestApiKeyFromSettings:
    def test_key_that_only_the_dotenv_file_provides_is_found(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / ".env").write_text("DDK_ANTHROPIC_API_KEY=sk-ant-from-dotenv\n")
        monkeypatch.chdir(tmp_path)

        result = PreflightDoctor(DdalggakConfig())._check_api_key()

        assert result["status"] == "pass"

    def test_without_settings_only_the_environment_counts(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        (tmp_path / ".env").write_text("DDK_ANTHROPIC_API_KEY=sk-ant-from-dotenv\n")
        monkeypatch.chdir(tmp_path)

        assert PreflightDoctor()._check_api_key()["status"] == "fail"


class TestToolsThatAreNotRequired:
    def test_missing_uv_only_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("shutil.which", lambda name: None)

        result = PreflightDoctor()._check_uv()

        assert (result["status"], result["critical"]) == ("warn", False)

    def test_missing_git_only_warns_because_runs_work_without_a_repository(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("shutil.which", lambda name: None)

        result = PreflightDoctor()._check_git()

        assert (result["status"], result["critical"]) == ("warn", False)
        assert "rollback" in result["detail"]

    def test_node_without_npm_warns_about_building(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "shutil.which", lambda name: "/usr/bin/node" if name == "node" else None
        )

        result = PreflightDoctor()._check_node()

        assert result["status"] == "warn"
        assert "npm" in result["detail"]


class TestBrowserCheck:
    def test_custom_chromium_path_that_exists_passes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        binary = tmp_path / "chrome"
        binary.write_text("")
        monkeypatch.setenv("DDK_CHROMIUM_PATH", str(binary))

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "pass"
        assert str(binary) in result["detail"]
        assert result["critical"] is False

    def test_custom_chromium_path_that_is_missing_warns(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("DDK_CHROMIUM_PATH", str(tmp_path / "nope"))

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "warn"
        assert "DDK_CHROMIUM_PATH" in result["detail"]

    def test_the_browser_a_run_would_use_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
        _probe(monkeypatch, PLAYWRIGHT_BUILD)

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "pass"
        assert result["detail"] == PLAYWRIGHT_BUILD
        assert result["critical"] is False

    def test_an_installed_chrome_is_named_as_the_stand_in(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
        _probe(monkeypatch, "/Applications/Google Chrome")

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "pass"
        assert "/Applications/Google Chrome" in result["detail"]
        assert "installed browser" in result["detail"]

    def test_no_browser_names_the_fixes_and_the_waiver(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
        _probe(
            monkeypatch,
            BrowserUnavailableError(
                "No Chromium found; run: ddk doctor --install-browser, install Google Chrome, "
                "or set DDK_CHROMIUM_PATH to an existing Chromium"
            ),
        )

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "warn"
        assert result["critical"] is False
        assert "ddk doctor --install-browser" in result["detail"]
        assert "Chrome" in result["detail"]
        assert "--no-visual" in result["detail"]

    def test_a_browser_that_cannot_start_says_why(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DDK_CHROMIUM_PATH", raising=False)
        _probe(monkeypatch, BrowserUnavailableError("Chromium could not start: kernel said no"))

        result = PreflightDoctor()._check_browser()

        assert result["status"] == "warn"
        assert "kernel said no" in result["detail"]

    def test_an_explicit_path_is_not_launched_just_to_check_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        binary = tmp_path / "chrome"
        binary.write_text("")
        monkeypatch.setenv("DDK_CHROMIUM_PATH", str(binary))
        _probe(monkeypatch, AssertionError("must not start a browser"))

        assert PreflightDoctor()._check_browser()["status"] == "pass"

    @pytest.mark.usefixtures("no_browser_start")
    def test_browser_check_is_part_of_the_run(self) -> None:
        names = [r["name"] for r in PreflightDoctor().run_checks()]

        assert "Headless Chromium" in names

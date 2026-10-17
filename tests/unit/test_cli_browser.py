"""A missing Chromium: ``doctor`` can fetch it, and ``run`` says so before it spends anything."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from ddk.adapters.chromium_browser import BrowserUnavailableError
from ddk.cli import app
from ddk.services.pipeline_runner import RuntimeServices
from tests.fakes import FakePlaywrightAdapter
from tests.fakes.images import write_png
from tests.fakes.runtime_services import stub_runtime_services

runner = CliRunner()


class TestDoctorInstallBrowser:
    pytestmark = pytest.mark.usefixtures("no_browser_start")

    def test_the_download_comes_before_the_checks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        downloads: list[str] = []
        monkeypatch.setattr(
            "ddk.cli.workspace.install_chromium", lambda: downloads.append("go") or True
        )

        result = runner.invoke(app, ["doctor", "--install-browser"])

        assert downloads == ["go"]
        assert result.output.index("내려받는 중") < result.output.index("Headless Chromium")

    def test_a_failed_download_stops_with_a_message(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ddk.cli.workspace.install_chromium", lambda: False)

        result = runner.invoke(app, ["doctor", "--install-browser"])

        assert result.exit_code == 4
        assert "내려받지 못했습니다" in result.output
        assert "Headless Chromium" not in result.output

    def test_without_the_option_nothing_is_downloaded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        downloads: list[str] = []
        monkeypatch.setattr(
            "ddk.cli.workspace.install_chromium", lambda: downloads.append("go") or True
        )

        runner.invoke(app, ["doctor"])

        assert downloads == []


class _MissingBrowser(FakePlaywrightAdapter):
    async def probe(self) -> str:
        raise BrowserUnavailableError(
            "No Chromium found; run: ddk doctor --install-browser, install Google Chrome, "
            "or set DDK_CHROMIUM_PATH to an existing Chromium"
        )


class _WorkingBrowser(FakePlaywrightAdapter):
    probes = 0

    async def probe(self) -> str:
        _WorkingBrowser.probes += 1
        return "fake browser"


def _services_with(browser: FakePlaywrightAdapter) -> RuntimeServices:
    return dataclasses.replace(stub_runtime_services(), browser=browser)


def _run(tmp_path: Path, services: RuntimeServices, *options: str) -> tuple[int, str]:
    image = write_png(tmp_path / "design.png")
    with patch("ddk.cli.delivery.build_runtime_services", lambda _cfg: services):
        result = runner.invoke(app, ["run", str(image), "--repo", str(tmp_path), *options])
    return result.exit_code, result.output


class TestRunFailsEarly:
    def test_a_missing_browser_stops_the_run_before_anything_is_created(
        self, tmp_path: Path
    ) -> None:
        code, output = _run(tmp_path, _services_with(_MissingBrowser()))

        assert code == 4
        assert "ddk doctor --install-browser" in output
        assert "--no-visual" in output
        assert not (tmp_path / ".ddk").exists()

    def test_waiving_the_comparison_does_not_need_a_browser(self, tmp_path: Path) -> None:
        _run(tmp_path, _services_with(_MissingBrowser()), "--no-visual")

        assert (tmp_path / ".ddk").exists()

    def test_a_working_browser_is_tried_once_and_the_run_goes_on(self, tmp_path: Path) -> None:
        _WorkingBrowser.probes = 0

        _run(tmp_path, _services_with(_WorkingBrowser()))

        assert _WorkingBrowser.probes == 1
        assert (tmp_path / ".ddk").exists()

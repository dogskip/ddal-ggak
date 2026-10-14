"""Visual-check settings: defaults, environment names, and what reaches the runtime."""

from __future__ import annotations

import pytest

from ddk.adapters.chromium_browser import ChromiumBrowserAdapter
from ddk.adapters.null_playwright import NullPlaywrightAdapter
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.cli.runtime import build_runtime_services
from ddk.models.config import DdalggakConfig


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "DDK_VISUAL_CHECK",
        "DDK_MAX_MISMATCH_RATIO",
        "DDK_CHROMIUM_PATH",
        "DDK_SSIM_THRESHOLD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-test")


def _config(**overrides: object) -> DdalggakConfig:
    return DdalggakConfig(**overrides)  # type: ignore[arg-type]


def test_defaults_check_the_page_against_the_design() -> None:
    cfg = _config()

    assert cfg.visual_check is True
    assert cfg.ssim_threshold == 0.92
    assert cfg.max_mismatch_ratio == 0.03
    assert cfg.chromium_path == ""


def test_environment_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_VISUAL_CHECK", "false")
    monkeypatch.setenv("DDK_MAX_MISMATCH_RATIO", "0.1")
    monkeypatch.setenv("DDK_CHROMIUM_PATH", "/opt/chromium/chrome")

    cfg = _config()

    assert (cfg.visual_check, cfg.max_mismatch_ratio, cfg.chromium_path) == (
        False,
        0.1,
        "/opt/chromium/chrome",
    )


def test_visual_runtime_uses_the_real_browser_and_preview() -> None:
    services = build_runtime_services(_config(chromium_path="/opt/chromium/chrome"))

    assert isinstance(services.browser, ChromiumBrowserAdapter)
    assert isinstance(services.preview, SubprocessPreviewLauncher)
    assert services.ssim_threshold == 0.92
    assert services.max_mismatch_ratio == 0.03


def test_waived_visual_runtime_has_no_browser() -> None:
    services = build_runtime_services(_config(visual_check=False))

    assert isinstance(services.browser, NullPlaywrightAdapter)
    assert services.preview is None

"""Builds the concrete services a pipeline run uses."""

from __future__ import annotations

from ddk.adapters.chromium_browser import ChromiumBrowserAdapter
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.local_git import LocalGitAdapter
from ddk.adapters.null_playwright import NullPlaywrightAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.adapters.subprocess_build_runner import SubprocessBuildRunner
from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
from ddk.i18n import t
from ddk.models.config import DdalggakConfig
from ddk.services.pipeline_runner import RuntimeServices

from .common import err_console, require_api_key
from .contract import CommandFailureError


def build_runtime_services(cfg: DdalggakConfig) -> RuntimeServices:
    """Build concrete runtime services for graph execution."""
    if cfg.llm_provider != "anthropic":
        err_console.print(t("❌ 아직 지원하지 않는 LLM provider: {name}", name=cfg.llm_provider))
        raise CommandFailureError("configuration", "unsupported_runtime_settings")
    if cfg.sandbox_mode != "tempdir":
        err_console.print(t("❌ 아직 지원하지 않는 sandbox mode: {name}", name=cfg.sandbox_mode))
        raise CommandFailureError("configuration", "unsupported_runtime_settings")

    require_api_key(cfg)

    from ddk.adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415

    browser: PlaywrightAdapter = (
        ChromiumBrowserAdapter(executable_path=cfg.chromium_path or None)
        if cfg.visual_check
        else NullPlaywrightAdapter()
    )
    return RuntimeServices(
        llm=ClaudeAdapter(
            api_key=cfg.anthropic_api_key,
            default_model=cfg.llm_model,
            cost_cap_usd=cfg.cost_cap_usd,
        ),
        filesystem=FilesystemAdapter(),
        git=LocalGitAdapter(),
        sandbox=TempDirSandbox(),
        build_runner=SubprocessBuildRunner(),
        browser=browser,
        screenshot_diff=LocalScreenshotDiffAdapter(),
        primary_model=cfg.llm_model,
        light_model=cfg.light_model,
        install_dependencies=cfg.install_dependencies,
        step_timeout_s=cfg.sandbox_timeout_seconds,
        max_fix_attempts=cfg.max_retry_attempts,
        preview=SubprocessPreviewLauncher() if cfg.visual_check else None,
        ssim_threshold=cfg.ssim_threshold,
        max_mismatch_ratio=cfg.max_mismatch_ratio,
    )

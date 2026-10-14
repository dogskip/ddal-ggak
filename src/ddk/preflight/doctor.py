"""PreflightDoctor — environment sanity checks — INFRA-07.

Usage::

    from ddk.preflight.doctor import PreflightDoctor

    doctor = PreflightDoctor()
    results = doctor.run_checks()
    ok = all(r["status"] != "fail" and not r["critical"] for r in results
             if r["critical"])
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

from ddk.adapters.chromium_browser import (
    PLAYWRIGHT_BUILD,
    BrowserUnavailableError,
    ChromiumBrowserAdapter,
)
from ddk.models.config import DdalggakConfig


class CheckResult(TypedDict):
    """Result of a single preflight check."""

    name: str
    status: str  # "pass" | "warn" | "fail"
    detail: str
    critical: bool


class PreflightDoctor:
    """Runs environment sanity checks before a ddk pipeline run.

    Checks:
    1. Python >= 3.12
    2. ``uv`` is on PATH
    3. At least one LLM API key env var is set
    4. Node.js is on PATH (for build runner)
    5. ``git`` version >= 2.28
    6. Headless Chromium for the screenshot comparison (optional)

    Pass the loaded settings so a key kept in ``.env`` counts; without them only the process
    environment is read.
    """

    def __init__(self, config: DdalggakConfig | None = None) -> None:
        self._config = config

    def run_checks(self) -> list[CheckResult]:
        """Execute all preflight checks and return results.

        Returns:
            Ordered list of :class:`CheckResult` dicts, one per check.
        """
        return [
            self._check_python(),
            self._check_uv(),
            self._check_api_key(),
            self._check_node(),
            self._check_git(),
            self._check_browser(),
        ]

    def check_browser(self) -> CheckResult:
        """Whether a headless Chromium is available for the screenshot comparison."""
        return self._check_browser()

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_python(self) -> CheckResult:
        ver = sys.version_info
        version_str = f"Python {ver.major}.{ver.minor}.{ver.micro}"
        if ver >= (3, 12):
            return CheckResult(
                name="Python >= 3.12",
                status="pass",
                detail=version_str,
                critical=True,
            )
        return CheckResult(
            name="Python >= 3.12",
            status="fail",
            detail=f"{version_str} — upgrade to 3.12+",
            critical=True,
        )

    def _check_uv(self) -> CheckResult:
        uv_path = shutil.which("uv")
        if uv_path:
            return CheckResult(
                name="uv package manager",
                status="pass",
                detail=f"found at {uv_path}",
                critical=True,
            )
        return CheckResult(
            name="uv package manager",
            status="warn",
            detail="not found on PATH — only needed to install ddk with uv (https://docs.astral.sh/uv/)",
            critical=False,
        )

    def _check_api_key(self) -> CheckResult:
        """Check the API keys for the provider that is actually implemented."""
        if self._config is not None and self._config.anthropic_api_key:
            return CheckResult(
                name="LLM API key",
                status="pass",
                detail="set (environment or .env)",
                critical=True,
            )
        key_vars = [
            "DDK_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY",
        ]
        found = [v for v in key_vars if os.environ.get(v)]
        if found:
            return CheckResult(
                name="LLM API key",
                status="pass",
                detail=f"{', '.join(found)} set",
                critical=True,
            )
        return CheckResult(
            name="LLM API key",
            status="fail",
            detail=("No LLM API key found. Set DDK_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY."),
            critical=True,
        )

    def _check_node(self) -> CheckResult:
        node_path = shutil.which("node")
        if not node_path:
            return CheckResult(
                name="Node.js",
                status="warn",
                detail="not found — the build, type and lint checks of a run need it",
                critical=False,
            )
        if not shutil.which("npm"):
            return CheckResult(
                name="Node.js",
                status="warn",
                detail=f"found at {node_path}, but npm is missing — builds in the sandbox need it",
                critical=False,
            )
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ver_str = result.stdout.strip()
        except Exception:  # noqa: BLE001
            ver_str = "unknown"
        return CheckResult(
            name="Node.js",
            status="pass",
            detail=f"found at {node_path} ({ver_str})",
            critical=False,
        )

    def _check_git(self) -> CheckResult:
        git_path = shutil.which("git")
        if not git_path:
            return CheckResult(
                name="git >= 2.28",
                status="warn",
                detail="git not found on PATH — ddk still runs, but checkpoints and rollback "
                "are unavailable",
                critical=False,
            )
        try:
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            raw = result.stdout.strip()  # e.g. "git version 2.43.0"
            parts = raw.split()
            # git --version: "git version 2.39.3 (Apple Git-155)" → find numeric version
            ver_str_raw = ""
            for part in parts:
                if part and part[0].isdigit():
                    ver_str_raw = part
                    break
            # Strip any trailing non-digit suffix like "(Apple"
            import re as _re  # noqa: PLC0415

            ver_match = _re.match(r"(\d+)\.(\d+)", ver_str_raw)
            major = int(ver_match.group(1)) if ver_match else 0
            minor = int(ver_match.group(2)) if ver_match else 0
            if (major, minor) >= (2, 28):
                return CheckResult(
                    name="git >= 2.28",
                    status="pass",
                    detail=raw,
                    critical=True,
                )
            return CheckResult(
                name="git >= 2.28",
                status="warn",
                detail=f"{raw} — git 2.28+ recommended for worktree support",
                critical=False,
            )
        except Exception as exc:  # noqa: BLE001
            return CheckResult(
                name="git >= 2.28",
                status="warn",
                detail=f"git check failed: {exc}",
                critical=False,
            )

    def _check_browser(self) -> CheckResult:
        name = "Headless Chromium"
        custom = os.environ.get("DDK_CHROMIUM_PATH", "")
        if custom:
            if Path(custom).is_file():
                return CheckResult(name=name, status="pass", detail=custom, critical=False)
            return CheckResult(
                name=name,
                status="warn",
                detail=f"DDK_CHROMIUM_PATH does not point to a file: {custom}",
                critical=False,
            )
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                used = asyncio.run(ChromiumBrowserAdapter().probe())
            else:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    used = executor.submit(self._probe_browser).result()
        except BrowserUnavailableError as exc:
            detail = f"{exc} (or skip the comparison with --no-visual)"
            return CheckResult(name=name, status="warn", detail=detail, critical=False)
        if used != PLAYWRIGHT_BUILD:
            used = f"{used} (installed browser, used because Playwright has no build)"
        return CheckResult(name=name, status="pass", detail=used, critical=False)

    @staticmethod
    def _probe_browser() -> str:
        return asyncio.run(ChromiumBrowserAdapter().probe())

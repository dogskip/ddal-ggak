"""Downloading the headless Chromium that Playwright drives."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from ddk.adapters import browser_install
from ddk.adapters.browser_install import install_chromium


def _installer_ends_with(monkeypatch: pytest.MonkeyPatch, outcome: int | Exception) -> list[Any]:
    commands: list[Any] = []

    def run(command: list[str], **_: Any) -> Any:
        commands.append(command)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(returncode=outcome)

    monkeypatch.setattr(browser_install.subprocess, "run", run)
    return commands


def test_it_runs_playwrights_installer_with_the_same_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands = _installer_ends_with(monkeypatch, 0)

    assert install_chromium() is True
    assert commands == [[sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"]]


def test_a_failed_download_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _installer_ends_with(monkeypatch, 1)

    assert install_chromium() is False


def test_an_installer_that_cannot_start_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    _installer_ends_with(monkeypatch, OSError("no interpreter"))

    assert install_chromium() is False

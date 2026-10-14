"""Finding a Chrome, Chromium or Edge that is already installed, so no download is needed."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from ddk.adapters import system_browser
from ddk.adapters.system_browser import find_system_browser


def _program(path: Path, *, executable: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR if executable else mode & ~stat.S_IXUSR)
    return path


@pytest.fixture(autouse=True)
def _nothing_installed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(system_browser, "_MAC_PATHS", (str(tmp_path / "no-mac-chrome"),))
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    for name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        monkeypatch.delenv(name, raising=False)


def test_nothing_installed_finds_nothing() -> None:
    assert find_system_browser("linux") is None
    assert find_system_browser("darwin") is None
    assert find_system_browser("win32") is None


class TestMac:
    def test_finds_chrome_in_the_applications_folder(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        chrome = _program(tmp_path / "Google Chrome")
        monkeypatch.setattr(system_browser, "_MAC_PATHS", (str(tmp_path / "gone"), str(chrome)))

        assert find_system_browser("darwin") == chrome

    def test_the_first_listed_browser_wins(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        first = _program(tmp_path / "a" / "chrome")
        second = _program(tmp_path / "b" / "edge")
        monkeypatch.setattr(system_browser, "_MAC_PATHS", (str(first), str(second)))

        assert find_system_browser("darwin") == first


class TestLinux:
    def test_finds_a_browser_on_the_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        binary = _program(tmp_path / "bin" / "chromium")
        monkeypatch.setenv("PATH", str(binary.parent))

        assert find_system_browser("linux") == binary

    def test_chrome_is_preferred_over_chromium(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _program(tmp_path / "bin" / "chromium")
        chrome = _program(tmp_path / "bin" / "google-chrome")
        monkeypatch.setenv("PATH", str(tmp_path / "bin"))

        assert find_system_browser("linux") == chrome

    @pytest.mark.skipif(os.name == "nt", reason="needs POSIX permissions")
    def test_a_file_that_cannot_run_is_skipped(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        _program(tmp_path / "bin" / "google-chrome", executable=False)
        monkeypatch.setenv("PATH", str(tmp_path / "bin"))

        assert find_system_browser("linux") is None


class TestWindows:
    @pytest.mark.parametrize("variable", ["PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"])
    def test_finds_chrome_under_the_usual_folders(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variable: str
    ) -> None:
        chrome = _program(tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe")
        monkeypatch.setenv(variable, str(tmp_path))

        assert find_system_browser("win32") == chrome

    def test_finds_edge_when_chrome_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        edge = _program(tmp_path / "Microsoft" / "Edge" / "Application" / "msedge.exe")
        monkeypatch.setenv("PROGRAMFILES", str(tmp_path))

        assert find_system_browser("win32") == edge

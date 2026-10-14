"""Find a Chrome, Chromium or Edge that is already installed, so no browser download is needed."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_MAC_PATHS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
)
_PATH_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
)
_WINDOWS_FOLDERS = ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")
_WINDOWS_PROGRAMS = (
    ("Google", "Chrome", "Application", "chrome.exe"),
    ("Microsoft", "Edge", "Application", "msedge.exe"),
)


def find_system_browser(platform: str = sys.platform) -> Path | None:
    """The first installed Chrome-family browser that can run, or ``None``.

    Chrome is preferred over Chromium, and Chromium over Edge.
    """
    for candidate in _candidates(platform):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def _candidates(platform: str) -> list[Path]:
    found: list[Path] = []
    if platform == "darwin":
        found.extend(Path(path) for path in _MAC_PATHS)
    if platform == "win32":
        for program in _WINDOWS_PROGRAMS:
            for variable in _WINDOWS_FOLDERS:
                root = os.environ.get(variable)
                if root:
                    found.append(Path(root, *program))
    found.extend(Path(path) for name in _PATH_NAMES if (path := shutil.which(name)))
    return found

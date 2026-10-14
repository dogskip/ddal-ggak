"""Download the headless Chromium that Playwright drives."""

from __future__ import annotations

import subprocess
import sys

_COMMAND = [sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"]


def install_chromium() -> bool:
    """Run Playwright's installer with this Python; its progress shows in the terminal."""
    try:
        return subprocess.run(_COMMAND, check=False).returncode == 0
    except OSError:
        return False

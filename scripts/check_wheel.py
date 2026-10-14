"""Fail unless a built wheel holds what ``ddk demo`` and ``ddk install`` need at run time.

Usage: ``uv build && python scripts/check_wheel.py dist/*.whl``
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

REQUIRED = (
    "ddk/__main__.py",
    "ddk/assets/demo/vite-app/package.json",
    "ddk/assets/demo/vite-app/package-lock.json",
    "ddk/assets/demo/vite-app/index.html",
    "ddk/assets/demo/vite-app/src/App.tsx",
    "ddk/assets/commands/claude/design.md",
    "ddk/assets/verified-change/contract.schema.json",
)
FORBIDDEN_PARTS = ("node_modules/", "__pycache__/", ".ddk/")


def problems(wheel: Path) -> list[str]:
    names = zipfile.ZipFile(wheel).namelist()
    found = [f"missing from the wheel: {path}" for path in REQUIRED if path not in names]
    for part in FORBIDDEN_PARTS:
        found.extend(f"must not be in the wheel: {name}" for name in names if part in name)
    return found


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: check_wheel.py <wheel>...", file=sys.stderr)
        return 2
    failed = False
    for path in paths:
        wheel = Path(path)
        found = problems(wheel)
        failed = failed or bool(found)
        print(f"{wheel.name}: {'FAIL' if found else 'ok'}")
        for line in found:
            print(f"  {line}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

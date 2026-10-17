"""Check runtime assets and publication boundaries in built distributions.

Usage: ``uv build && python scripts/check_wheel.py dist/*``
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

REQUIRED = (
    "ddk/__main__.py",
    "ddk/assets/benchmarks/paired-corpus.json",
    "ddk/assets/demo/vite-app/package.json",
    "ddk/assets/demo/vite-app/package-lock.json",
    "ddk/assets/demo/vite-app/index.html",
    "ddk/assets/demo/vite-app/src/App.tsx",
    "ddk/assets/skills/ddk-design/SKILL.md",
    "ddk/assets/skills/ddk-verify/SKILL.md",
    "ddk/assets/skills/ddk-evidence/SKILL.md",
    "ddk/assets/skills/ddk-verify/references/ddk-verify.md",
    "ddk/assets/skills/ddk-evidence/references/ddk-evidence.md",
    "ddk/assets/verified-change/contract.schema.json",
    "ddk/assets/verified-change/chromium-seccomp.json",
    "ddk/assets/verified-change/LICENSE-moby",
)
FORBIDDEN_PARTS = (
    "ddal-ggak-clean/",
    "node_modules/",
    "__pycache__/",
    ".ddk/",
    ".planning/",
    "evidence/",
    "docs/design/",
    "docs/superpowers/",
    "docs/launch/",
    "test-results/",
    "playwright-report/",
)


def problems(wheel: Path) -> list[str]:
    if wheel.name.endswith(".tar.gz"):
        with tarfile.open(wheel) as archive:
            names = [name.partition("/")[2] for name in archive.getnames()]
        required = tuple("src/" + path for path in REQUIRED) + (
            "tests/fixtures/verified-change/contract-examples.json",
        )
    else:
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
        required = REQUIRED
    found = [f"missing from the distribution: {path}" for path in required if path not in names]
    for part in FORBIDDEN_PARTS:
        found.extend(
            f"must not be in the distribution: {name}"
            for name in names
            if name.startswith(part) or "/" + part in name
        )
    return found


def main(paths: list[str]) -> int:
    if not paths:
        print("usage: check_wheel.py <wheel-or-sdist>...", file=sys.stderr)
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

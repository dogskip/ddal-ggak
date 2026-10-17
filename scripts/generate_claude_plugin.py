"""Render the three canonical skills with Claude's plugin command names."""

from __future__ import annotations

import argparse
from pathlib import Path

from ddk.installer import skills


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    destination = root / "plugins" / "claude" / "skills"
    expected = {}
    for skill in skills():
        short = skill.parent.name.removeprefix("ddk-")
        for source in skill.parent.rglob("*"):
            if not source.is_file():
                continue
            payload = source.read_bytes()
            if source == skill:
                payload = payload.replace(
                    f"name: {skill.parent.name}\n".encode(), f"name: {short}\n".encode(), 1
                )
            expected[destination / short / source.relative_to(skill.parent)] = payload
    failures = []
    for path, payload in expected.items():
        if args.check:
            if not path.is_file() or path.read_bytes() != payload:
                failures.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    extras = {p for p in destination.rglob("*") if p.is_file()} - expected.keys()
    failures.extend(str(path.relative_to(root)) for path in sorted(extras))
    if failures:
        print("stale Claude skill adapters: " + ", ".join(failures))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())

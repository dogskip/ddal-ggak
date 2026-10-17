"""Generate README host support tables from the installation registry."""

from __future__ import annotations

import argparse
from pathlib import Path

from ddk.installer import HOSTS

START = "<!-- ddk-hosts:start -->"
END = "<!-- ddk-hosts:end -->"


def table(korean: bool = False) -> str:
    title = (
        "| 도구 | 프로젝트 파일 | 전역 파일 | MCP 설정 |"
        if korean
        else "| Host | Project file | Global file | MCP settings |"
    )
    rows = [START, title, "| --- | --- | --- | --- |"]
    for host, adapter in HOSTS.items():
        global_path = (
            f"`{adapter.global_path}`"
            if adapter.global_path
            else ("미지원" if korean else "unsupported")
        )
        mcp = f"`{adapter.mcp_project}`" if adapter.mcp_project else "—"
        rows.append(
            f"| [{host}]({adapter.docs[0]}) | `{adapter.project}` | {global_path} | {mcp} |"
        )
    return "\n".join([*rows, END])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    failures = []
    for name, ko in [("README.md", False), ("README.ko.md", True)]:
        p = root / name
        old = p.read_text()
        generated = table(ko)
        if START in old:
            before, remainder = old.split(START, 1)
            _, after = remainder.split(END, 1)
            new = before + generated + after
        else:
            new = old + "\n" + generated + "\n"
        if args.check:
            if new != old:
                failures.append(name)
        else:
            p.write_text(new)
    if failures:
        print("stale host tables: " + ", ".join(failures))
    return bool(failures)


if __name__ == "__main__":
    raise SystemExit(main())

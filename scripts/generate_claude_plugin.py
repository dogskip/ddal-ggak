"""Render canonical skill bodies into Claude's documented command-map format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ddk.installer import skills


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    path = repository / ".claude-plugin/plugin.json"
    original = path.read_text()
    plugin = json.loads(original)
    commands = {}
    for skill in skills():
        _, header, body = skill.read_text().split("---", 2)
        description = next(
            line.removeprefix("description:").strip()
            for line in header.splitlines()
            if line.startswith("description:")
        )
        reference = (
            "${CLAUDE_PLUGIN_ROOT}/src/ddk/assets/skills/" + skill.parent.name + "/references/"
        )
        commands[skill.parent.name.removeprefix("ddk-")] = {
            "description": description,
            "content": body.lstrip().replace("references/", reference),
        }
    plugin["skills"] = ["./src/ddk/assets/skills/"]
    plugin["commands"] = commands
    expected = json.dumps(plugin, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if expected != original:
            print("stale Claude command adapters")
            return 1
    else:
        path.write_text(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

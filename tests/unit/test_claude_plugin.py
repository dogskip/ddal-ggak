"""The local plugin references canonical skills and the existing fail-closed gate."""

import json
from pathlib import Path

from ddk.services import verified_hooks

ROOT = Path(__file__).resolve().parents[2]


def test_plugin_components_use_canonical_sources():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "ddk"
    assert plugin["skills"] == ["./src/ddk/assets/skills/"]
    assert set(plugin["commands"]) == {"design", "verify", "evidence"}
    for short, command in plugin["commands"].items():
        skill = ROOT / "src/ddk/assets/skills" / ("ddk-" + short) / "SKILL.md"
        _, header, body = skill.read_text().split("---", 2)
        reference = (
            "${CLAUDE_PLUGIN_ROOT}/src/ddk/assets/skills/" + skill.parent.name + "/references/"
        )
        assert command["content"] == body.lstrip().replace("references/", reference)
        assert command["description"] in header
    assert plugin["mcpServers"] == {"ddk": {"command": "ddk", "args": ["serve"]}}
    hook = plugin["hooks"]["Stop"][0]["hooks"][0]
    assert hook["command"] == verified_hooks._STOP
    assert hook["type"] == "command" and hook["timeout"] == 60
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert marketplace["plugins"][0]["name"] == plugin["name"]
    assert marketplace["plugins"][0]["source"] == "./"

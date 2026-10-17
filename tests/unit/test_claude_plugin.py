"""The local plugin references canonical skills and the existing fail-closed gate."""

import json
from pathlib import Path

from ddk.services import verified_hooks

ROOT = Path(__file__).resolve().parents[2]


def test_plugin_components_use_canonical_sources():
    plugin = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert plugin["name"] == "ddk"
    assert plugin["skills"] == ["./plugins/claude/skills/"]
    skills = ROOT / "plugins/claude/skills"
    assert sorted(p.name for p in skills.iterdir()) == ["design", "evidence", "verify"]
    for path in skills.iterdir():
        canonical = ROOT / "src/ddk/assets/skills" / ("ddk-" + path.name) / "SKILL.md"
        expected = canonical.read_text().replace("name: ddk-" + path.name, "name: " + path.name, 1)
        assert (path / "SKILL.md").read_text() == expected
    assert plugin["mcpServers"] == {"ddk": {"command": "ddk", "args": ["serve"]}}
    hook = plugin["hooks"]["Stop"][0]["hooks"][0]
    assert hook["command"] == verified_hooks._STOP
    assert hook["type"] == "command" and hook["timeout"] == 60
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert marketplace["plugins"][0]["name"] == plugin["name"]
    assert marketplace["plugins"][0]["source"] == "./"

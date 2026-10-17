"""Unit tests for installer and command template registration."""

from __future__ import annotations

import json
from pathlib import Path

from ddk import installer


def test_install_claude_copies_command_and_registers_mcp(tmp_path: Path) -> None:
    result = installer.install_claude(tmp_path)

    assert result.success is True
    command_path = tmp_path / ".claude" / "skills" / "ddk-design" / "SKILL.md"
    settings_path = tmp_path / ".mcp.json"
    assert command_path.exists()
    assert settings_path.exists()

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["mcpServers"]["ddk"] == {
        "command": "ddk",
        "args": ["serve"],
    }


def test_install_opencode_copies_command_and_registers_nested_mcp(tmp_path: Path) -> None:
    result = installer.install_opencode(tmp_path)

    assert result.success is True
    command_path = tmp_path / ".opencode" / "commands" / "ddk-design.md"
    config_path = tmp_path / "opencode.json"
    assert command_path.exists()
    assert config_path.exists()

    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert config["mcp"]["ddk"] == {
        "type": "local",
        "command": ["ddk", "serve"],
        "enabled": True,
    }


def test_detect_tools_uses_project_markers(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".github").mkdir()

    detected = installer.detect_tools(tmp_path)

    assert set(detected) >= {"claude", "cursor", "copilot"}


def test_all_command_asset_directories_have_markdown_templates() -> None:
    asset_root = Path(installer.__file__).parent / "assets" / "skills"

    template_dirs = sorted(path for path in asset_root.iterdir() if path.is_dir())
    assert template_dirs
    for template_dir in template_dirs:
        markdown_files = sorted(template_dir.glob("*.md"))
        assert markdown_files, f"Expected markdown templates in {template_dir}"

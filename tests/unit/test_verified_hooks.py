from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from ddk import installer
from ddk.cli import app
from tests.unit.test_case_bootstrapper import setup_repo


def test_existing_invalid_claude_settings_are_never_replaced(tmp_path):
    folder = tmp_path / ".claude"
    folder.mkdir()
    path = tmp_path / ".mcp.json"
    path.write_bytes(b"{broken json")
    with pytest.raises(ValueError):
        installer.install_claude(tmp_path)
    assert path.read_bytes() == b"{broken json"


def test_settings_symlink_is_rejected_without_touching_external_bytes(tmp_path):
    folder = tmp_path / ".claude"
    folder.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text('{"keep":true}')
    (tmp_path / ".mcp.json").symlink_to(outside)
    with pytest.raises((ValueError, OSError)):
        installer.install_claude(tmp_path)
    assert outside.read_text() == '{"keep":true}'


def test_opt_in_hooks_preserve_existing_settings_and_are_idempotent(tmp_path):
    setup_repo(tmp_path)
    folder = tmp_path / ".claude"
    folder.mkdir()
    path = folder / "settings.json"
    path.write_text(
        json.dumps(
            {
                "keep": True,
                "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo existing"}]}]},
            }
        )
    )
    installer.install_hooks(tmp_path)
    first = path.read_bytes()
    installer.install_hooks(tmp_path)
    assert path.read_bytes() == first
    config = json.loads(first)
    assert config["keep"] is True
    commands = [h["command"] for group in config["hooks"]["Stop"] for h in group["hooks"]]
    assert commands[0] == "echo existing"
    assert any("ddk change gate" in c and "exit 2" in c for c in commands)
    hook = tmp_path / ".git/hooks/pre-push"
    assert "ddk change gate" in hook.read_text()
    assert hook.stat().st_mode & 0o777 == 0o755


def test_existing_git_hook_or_external_hooks_path_is_preserved_and_refused(tmp_path):
    setup_repo(tmp_path)
    hook = tmp_path / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\\necho keep\\n")
    original = hook.read_bytes()
    with pytest.raises(ValueError, match="hook_conflict"):
        installer.install_hooks(tmp_path)
    assert hook.read_bytes() == original
    assert not (tmp_path / ".claude/settings.json").exists()
    hook.unlink()
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "core.hooksPath", "../outside-hooks"], check=True
    )
    with pytest.raises(ValueError, match="external_hooks_path"):
        installer.install_hooks(tmp_path)


def test_hook_install_is_explicit_and_project_only(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["install", "--all", "--with-hooks", "--global"])
    assert result.exit_code != 0
    assert not (tmp_path / ".claude").exists()


def test_installed_public_commands_match_git_modes_and_private_settings_stay_private(tmp_path):
    from ddk.services.source_snapshot import capture_git_source, capture_git_worktree

    setup_repo(tmp_path)
    installer.install_cursor(tmp_path)
    installer.install_claude(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", ".cursor"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "installed commands"], check=True)
    assert (
        capture_git_source(tmp_path, "HEAD").tree_sha256
        == capture_git_worktree(tmp_path).tree_sha256
    )
    assert (tmp_path / ".mcp.json").stat().st_mode & 0o777 == 0o600

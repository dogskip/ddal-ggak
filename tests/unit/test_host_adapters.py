"""Official host formats and reversible, conflict-aware installation."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk import installer
from ddk.cli import app


def files(directory: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(directory).as_posix(): (p.read_bytes(), p.stat().st_mode & 0o777)
        for p in directory.rglob("*")
        if p.is_file()
    }


@pytest.mark.parametrize(
    "host", ["claude", "gemini", "opencode", "codex", "copilot", "cursor", "kiro"]
)
def test_install_uninstall_restores_original_bytes_and_tree(tmp_path: Path, host: str) -> None:
    config = {
        "claude": ".mcp.json",
        "opencode": "opencode.json",
        "cursor": ".cursor/mcp.json",
        "codex": ".codex/config.toml",
    }.get(host)
    if config:
        p = tmp_path / config
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(
            b'# keep formatting\nmodel = "existing"\n'
            if host == "codex"
            else b'{ "keep" : true }\n'
        )
    before = files(tmp_path)
    dirs = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()}
    installed = installer.install_host(host, tmp_path)
    assert installed.success, installed.message
    installer.install_host(host, tmp_path)
    result = installer.uninstall_hosts([host], tmp_path)
    assert result["status"] == "ok", result
    assert files(tmp_path) == before
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_dir()} == dirs


def test_official_paths_and_payloads(tmp_path: Path) -> None:
    for host in installer.HOSTS:
        installer.install_host(host, tmp_path)
    assert (tmp_path / ".claude/skills/ddk-design/SKILL.md").read_text().startswith("---\n")
    assert (tmp_path / ".agents/skills/ddk-design/SKILL.md").is_file()
    assert tomllib.loads((tmp_path / ".gemini/commands/ddk/design.toml").read_text())["prompt"]
    for path in [
        ".opencode/commands/ddk-design.md",
        ".github/prompts/ddk-design.prompt.md",
        ".cursor/rules/ddk-design.mdc",
        ".kiro/steering/ddk-design.md",
    ]:
        assert (tmp_path / path).read_text().startswith("---\n")
    assert json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]["ddk"]["command"] == "ddk"
    assert json.loads((tmp_path / "opencode.json").read_text())["mcp"]["ddk"] == {
        "type": "local",
        "command": ["ddk", "serve"],
        "enabled": True,
    }
    assert json.loads((tmp_path / ".cursor/mcp.json").read_text())["mcpServers"]["ddk"]["args"] == [
        "serve"
    ]
    assert tomllib.loads((tmp_path / ".codex/config.toml").read_text())["mcp_servers"]["ddk"][
        "args"
    ] == ["serve"]
    assert not (tmp_path / ".codex/commands").exists()
    assert not (tmp_path / ".claude/settings.json").exists()


def test_all_dry_run_json_uses_only_detected_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(installer, "detect_tools", lambda *_: ["gemini"])
    result = CliRunner().invoke(app, ["install", "--all", "--dry-run", "--json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["schema_version"] == "ddk/2"
    assert [r["host"] for r in data["data"]["hosts"]] == ["gemini"]
    assert files(tmp_path) == {}
    assert list(tmp_path.iterdir()) == []


def test_edited_file_is_a_conflict_and_is_not_removed(tmp_path: Path) -> None:
    result = installer.install_host("gemini", tmp_path)
    path = result.installed_files[0]
    path.write_text("user modification")
    result = installer.uninstall_hosts(["gemini"], tmp_path)
    assert result["status"] == "blocked"
    assert path.read_text() == "user modification"
    assert result["conflicts"]
    assert (tmp_path / ".ddk/install-manifest.json").is_file()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "invalid"])
def test_unsafe_config_fails_before_installing_assets(tmp_path: Path, kind: str) -> None:
    outside = tmp_path / "keep.json"
    outside.write_text('{"keep":true}')
    path = tmp_path / ".mcp.json"
    if kind == "symlink":
        path.symlink_to(outside)
    elif kind == "hardlink":
        path.hardlink_to(outside)
    else:
        path.write_text("{broken")
    with pytest.raises((OSError, ValueError)):
        installer.install_host("claude", tmp_path)
    assert outside.read_text() == '{"keep":true}'
    assert not (tmp_path / ".claude/skills").exists()


def test_partial_uninstall_keeps_other_hosts_and_can_resume(tmp_path: Path) -> None:
    installer.install_host("claude", tmp_path)
    installer.install_host("gemini", tmp_path)
    assert installer.uninstall_hosts(["claude"], tmp_path)["status"] == "ok"
    assert (tmp_path / ".gemini/commands/ddk/design.toml").is_file()
    assert installer.uninstall_hosts(["gemini"], tmp_path)["status"] == "ok"
    assert list(tmp_path.iterdir()) == []


def test_host_settings_are_never_source_inputs() -> None:
    from ddk.security.repo_paths import normalize_source_path

    for path in [".mcp.json", ".cursor/mcp.json", ".codex/config.toml", "opencode.json"]:
        with pytest.raises(ValueError):
            normalize_source_path(path)
    assert normalize_source_path(".cursor/rules/ddk-design.mdc")


def test_canonical_skills_follow_agent_skills_specification() -> None:
    import re

    for path in installer.skills():
        text = path.read_text()
        assert text.startswith("---\n")
        header = text.split("---", 2)[1]
        fields = dict(line.split(": ", 1) for line in header.strip().splitlines())
        name = fields["name"]
        assert name == path.parent.name
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name)
        assert len(name) <= 64
        assert 0 < len(fields["description"]) <= 1024
        assert len(text.splitlines()) <= 500


def test_generated_host_tables_are_current() -> None:
    from scripts.generate_host_table import END, START, table

    root = Path(__file__).resolve().parents[2]
    for name, ko in [("README.md", False), ("README.ko.md", True)]:
        text = (root / name).read_text()
        assert START + text.split(START)[1].split(END)[0] + END == table(ko)


def test_config_race_cannot_overwrite_new_user_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = installer._mcp_payload

    def mutate(path, adapter):
        payload = original(path, adapter)
        path.write_text('{"new_user_key":true}')
        return payload

    monkeypatch.setattr(installer, "_mcp_payload", mutate)
    with pytest.raises(ValueError, match="install_configuration_changed"):
        installer.install_host("claude", tmp_path)
    assert json.loads((tmp_path / ".mcp.json").read_text()) == {"new_user_key": True}
    assert not (tmp_path / ".claude").exists()


def test_uninstall_does_not_follow_replaced_parent_directory(tmp_path: Path) -> None:
    installer.install_host("cursor", tmp_path)
    (tmp_path / ".cursor").rename(tmp_path / "saved")
    foreign = tmp_path / "foreign"
    (foreign / "rules").mkdir(parents=True)
    (tmp_path / ".cursor").symlink_to(foreign, target_is_directory=True)
    result = installer.uninstall_hosts(["cursor"], tmp_path)
    assert result["status"] == "blocked"
    assert (foreign / "rules").is_dir()


def test_opt_in_hooks_are_removed_only_when_owned_and_unchanged(tmp_path: Path) -> None:
    from tests.unit.test_case_bootstrapper import setup_repo

    setup_repo(tmp_path)
    existing = tmp_path / ".claude/settings.json"
    existing.parent.mkdir()
    existing.write_bytes(b'{ "keep" : true }\n')
    before = files(tmp_path)
    installer.install_host("claude", tmp_path)
    installer.install_hooks(tmp_path)
    installer.install_hooks(tmp_path)
    assert installer.uninstall_hosts(["claude"], tmp_path)["status"] == "ok"
    assert files(tmp_path) == before

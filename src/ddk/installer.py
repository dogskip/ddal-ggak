"""Render canonical skills into documented host formats and track owned changes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import tomllib
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, Field

from ddk.models.verified_change import Record, object_record
from ddk.security.file_access import file_identity, parent_descriptor, read_regular
from ddk.services.durable_files import OwnedLock, atomic_write, ensure_directory
from ddk.services.verified_hooks import git_hook_bytes, read_settings, write_settings
from ddk.services.verified_hooks import install_hooks as _install_hooks
from ddk.services.verified_hooks import prepare_hooks as prepare_hooks

ASSETS = Path(__file__).parent / "assets" / "skills"
MANIFEST = ".ddk/install-manifest.json"
LIMIT = 2 * 1024**2


@dataclass(frozen=True)
class HostAdapter:
    project: str
    global_path: str | None
    format: Literal["skill", "md", "toml", "prompt.md", "mdc", "steering"]
    mcp_project: str | None
    mcp_global: str | None
    mcp_key: str | None
    docs: tuple[str, ...]


HOSTS: dict[str, HostAdapter] = {
    "claude": HostAdapter(
        ".claude/skills/{name}/SKILL.md",
        ".claude/skills/{name}/SKILL.md",
        "skill",
        ".mcp.json",
        None,
        "mcpServers",
        ("https://code.claude.com/docs/en/skills", "https://code.claude.com/docs/en/mcp"),
    ),
    "gemini": HostAdapter(
        ".gemini/commands/ddk/{short}.toml",
        ".gemini/commands/ddk/{short}.toml",
        "toml",
        None,
        None,
        None,
        ("https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/custom-commands.md",),
    ),
    "opencode": HostAdapter(
        ".opencode/commands/{name}.md",
        ".config/opencode/commands/{name}.md",
        "md",
        "opencode.json",
        ".config/opencode/opencode.json",
        "mcp",
        ("https://opencode.ai/docs/commands/", "https://opencode.ai/docs/mcp-servers/"),
    ),
    "codex": HostAdapter(
        ".agents/skills/{name}/SKILL.md",
        ".agents/skills/{name}/SKILL.md",
        "skill",
        ".codex/config.toml",
        ".codex/config.toml",
        "mcp_servers",
        ("https://developers.openai.com/codex/skills", "https://developers.openai.com/codex/mcp"),
    ),
    "copilot": HostAdapter(
        ".github/prompts/{name}.prompt.md",
        None,
        "prompt.md",
        None,
        None,
        None,
        ("https://code.visualstudio.com/docs/copilot/customization/prompt-files",),
    ),
    "cursor": HostAdapter(
        ".cursor/rules/{name}.mdc",
        None,
        "mdc",
        ".cursor/mcp.json",
        ".cursor/mcp.json",
        "mcpServers",
        ("https://cursor.com/docs/context/rules", "https://cursor.com/docs/context/mcp"),
    ),
    "kiro": HostAdapter(
        ".kiro/steering/{name}.md",
        ".kiro/steering/{name}.md",
        "steering",
        None,
        None,
        None,
        ("https://kiro.dev/docs/steering/",),
    ),
}


@dataclass
class InstallResult:
    tool: str
    success: bool
    installed_files: list[Path] = field(default_factory=lambda: cast(list[Path], []))
    message: str = ""
    actions: list[str] = field(default_factory=lambda: cast(list[str], []))


class InstalledFile(BaseModel):
    host: str
    path: str
    sha256: str
    before: str | None = None
    mode: int = 0o644
    before_mode: int = 0o644
    added_keys: list[str] = Field(default_factory=list)


class InstallManifest(BaseModel):
    schema_version: Literal["ddk-install/1"] = "ddk-install/1"
    files: list[InstalledFile] = Field(default_factory=lambda: cast(list[InstalledFile], []))
    directories: list[str] = Field(default_factory=list)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read(path: Path) -> tuple[bytes | None, tuple[int, ...] | None, int]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None, None, 0o644
    data = read_regular(path, LIMIT)
    if file_identity(path.lstat()) != file_identity(info):
        raise ValueError("install_file_changed")
    return data, file_identity(info), stat.S_IMODE(info.st_mode)


def _manifest(base: Path) -> tuple[InstallManifest, tuple[int, ...] | None]:
    data, identity, _ = _read(base / MANIFEST)
    manifest = InstallManifest.model_validate_json(data) if data is not None else InstallManifest()
    for entry in manifest.files:
        if entry.host not in HOSTS or entry.path not in _allowed_paths(HOSTS[entry.host]):
            raise ValueError("invalid_install_manifest_path")
        if entry.before is not None:
            base64.b64decode(entry.before, validate=True)
    allowed_directories = {".ddk"}
    for adapter in HOSTS.values():
        for name in _allowed_paths(adapter):
            allowed_directories.update(p.as_posix() for p in Path(name).parents if p != Path("."))
    for name in manifest.directories:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("invalid_install_manifest_directory")
        if name not in allowed_directories:
            raise ValueError("invalid_install_manifest_directory")
    return manifest, identity


def skills() -> list[Path]:
    return sorted(ASSETS.glob("*/SKILL.md"))


def _allowed_paths(adapter: HostAdapter) -> set[str]:
    paths: set[str] = set()
    for template in (adapter.project, adapter.global_path):
        if template:
            for skill in skills():
                target = Path(
                    template.format(
                        name=skill.parent.name, short=skill.parent.name.removeprefix("ddk-")
                    )
                )
                paths.add(target.as_posix())
                for reference in skill.parent.glob("references/*"):
                    paths.add((target.parent / "references" / reference.name).as_posix())
    paths.update(p for p in (adapter.mcp_project, adapter.mcp_global) if p)
    if adapter is HOSTS["claude"]:
        paths.update({".claude/settings.json", ".git/hooks/pre-push"})
    return paths


def _render(skill: Path, adapter: HostAdapter) -> bytes:
    text = read_regular(skill, LIMIT).decode("utf-8")
    _, header, body = text.split("---", 2)
    description = next(
        line.partition(":")[2].strip()
        for line in header.splitlines()
        if line.startswith("description:")
    )
    if adapter.format == "skill":
        return text.encode()
    if adapter.format == "toml":
        prompt = json.dumps(body.strip() + "\nRequest: {{args}}")
        return (f"description = {json.dumps(description)}\nprompt = {prompt}\n").encode()
    if adapter.format == "mdc":
        header = f"description: {description}\nalwaysApply: false\n"
    elif adapter.format == "steering":
        header = "inclusion: manual\n"
    else:
        header = f"description: {description}\n"
    return f"---\n{header}---\n{body}".encode()


def _mcp_payload(
    path: Path, adapter: HostAdapter
) -> tuple[bytes, list[str], tuple[int, ...] | None]:
    if adapter.mcp_key == "mcp_servers":
        raw, identity, _ = _read(path)
        config = tomllib.loads((raw or b"").decode())
        servers = config.get("mcp_servers", {})
        if not isinstance(servers, dict) or "ddk" in servers:
            raise ValueError("mcp_configuration_conflict")
        payload = (raw or b"") + b'\n[mcp_servers.ddk]\ncommand = "ddk"\nargs = ["serve"]\n'
        tomllib.loads(payload.decode())
        return payload, ["mcp_servers.ddk"], identity
    config, identity = read_settings(path)
    section = object_record(config.setdefault(adapter.mcp_key or "mcpServers", {}))
    if "ddk" in section:
        raise ValueError("mcp_configuration_conflict")
    section["ddk"] = (
        {"type": "local", "command": ["ddk", "serve"], "enabled": True}
        if adapter.mcp_key == "mcp"
        else {"command": "ddk", "args": ["serve"]}
    )
    return (
        (json.dumps(config, ensure_ascii=False, indent=2) + "\n").encode(),
        [f"{adapter.mcp_key}.ddk"],
        identity,
    )


def install_plan(host: str, base: Path, *, global_scope: bool = False) -> Record:
    adapter = HOSTS[host]
    template = adapter.global_path if global_scope else adapter.project
    if template is None:
        raise ValueError(f"unsupported_global_scope:{host}:use_project_or_AGENTS.md")
    paths: list[str] = []
    for skill in skills():
        target = Path(
            template.format(name=skill.parent.name, short=skill.parent.name.removeprefix("ddk-"))
        )
        paths.append(target.as_posix())
        paths.extend(
            (target.parent / "references" / p.name).as_posix()
            for p in skill.parent.glob("references/*")
        )
    mcp = adapter.mcp_global if global_scope else adapter.mcp_project
    if mcp:
        paths.append(mcp)
    actions = (
        ["claude mcp add --scope user ddk -- ddk serve"]
        if host == "claude" and global_scope
        else []
    )
    return {
        "host": host,
        "paths": paths,
        "actions": actions,
        "scope": "global" if global_scope else "project",
    }


def _make_directories(base: Path, path: Path, manifest: InstallManifest) -> None:
    missing = [p for p in path.parents if p != base and p.is_relative_to(base) and not p.exists()]
    ensure_directory(path.parent)
    for p in reversed(missing):
        name = p.relative_to(base).as_posix()
        if name not in manifest.directories:
            manifest.directories.append(name)


def install_host(
    host: str, target_dir: Path | None = None, *, global_scope: bool = False
) -> InstallResult:
    base = Path(os.path.abspath(target_dir or Path.cwd()))
    adapter = HOSTS[host]
    plan = install_plan(host, base, global_scope=global_scope)
    manifest, _ = _manifest(base)
    template = adapter.global_path if global_scope else adapter.project
    assert template is not None
    prepared: list[tuple[Path, bytes, list[str], int]] = []
    config_identities: dict[Path, tuple[int, ...] | None] = {}
    for skill in skills():
        relative = Path(
            template.format(name=skill.parent.name, short=skill.parent.name.removeprefix("ddk-"))
        )
        prepared.append((base / relative, _render(skill, adapter), [], 0o644))
        for reference in skill.parent.glob("references/*"):
            prepared.append(
                (
                    base / relative.parent / "references" / reference.name,
                    read_regular(reference, LIMIT),
                    [],
                    0o644,
                )
            )
    mcp = adapter.mcp_global if global_scope else adapter.mcp_project
    if mcp:
        path = base / mcp
        owned = next((e for e in manifest.files if e.host == host and e.path == mcp), None)
        if owned is not None:
            raw, config_identity, _ = _read(path)
            if raw is None or _sha(raw) != owned.sha256:
                raise ValueError("install_conflict")
            payload, keys = raw, owned.added_keys
        else:
            payload, keys, config_identity = _mcp_payload(path, adapter)
        config_identities[path] = config_identity
        prepared.append((path, payload, keys, 0o600))
    writes: list[tuple[Path, bytes, tuple[int, ...] | None, InstalledFile]] = []
    for path, payload, keys, mode in prepared:
        raw, identity, old_mode = _read(path)
        if path in config_identities and identity != config_identities[path]:
            raise ValueError("install_configuration_changed")
        relative_name = path.relative_to(base).as_posix()
        old = next((e for e in manifest.files if e.path == relative_name), None)
        if old is not None:
            if old.host != host or raw is None or _sha(raw) != old.sha256:
                raise ValueError("install_conflict")
            entry = old.model_copy(update={"sha256": _sha(payload)})
        else:
            if raw is not None and not keys:
                raise ValueError("install_conflict")
            entry = InstalledFile(
                host=host,
                path=relative_name,
                sha256=_sha(payload),
                before=base64.b64encode(raw).decode() if raw is not None else None,
                before_mode=old_mode,
                mode=mode,
                added_keys=keys,
            )
        writes.append((path, payload, identity, entry))
    _make_directories(base, base / MANIFEST, manifest)
    lock = OwnedLock(base / ".ddk/install.lock", str(uuid4())).acquire()
    try:
        current, manifest_identity = _manifest(base)
        if current.files != manifest.files:
            raise ValueError("install_manifest_changed")
        for path, payload, identity, entry in writes:
            _make_directories(base, path, manifest)
            atomic_write(
                path,
                payload,
                mode=entry.mode,
                exclusive=identity is None,
                expected_identity=identity,
            )
            manifest.files = [e for e in manifest.files if e.path != entry.path] + [entry]
            write_settings(base / MANIFEST, manifest.model_dump(), manifest_identity)
            manifest_identity = file_identity((base / MANIFEST).lstat())
    finally:
        lock.release()
    return InstallResult(host, True, [p for p, *_ in writes], "installed", list(plan["actions"]))


def install_hooks(repository: Path) -> list[Path]:
    base = Path(os.path.abspath(repository))
    hook, settings, config, _ = prepare_hooks(base)
    if not hook.is_relative_to(base):
        raise ValueError("hook_outside_project")
    desired = {
        hook: git_hook_bytes(),
        settings: (
            json.dumps(config, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        ).encode(),
    }
    before = {path: _read(path) for path in desired}
    manifest, identity = _manifest(base)
    for path, (raw, _, _) in before.items():
        owned = next(
            (e for e in manifest.files if e.path == path.relative_to(base).as_posix()), None
        )
        if owned is not None and (raw is None or _sha(raw) != owned.sha256):
            raise ValueError("install_conflict")
    _make_directories(base, base / MANIFEST, manifest)
    lock = OwnedLock(base / ".ddk/install.lock", str(uuid4())).acquire()
    try:
        current, current_identity = _manifest(base)
        if current.files != manifest.files or current_identity != identity:
            raise ValueError("install_manifest_changed")
        for path in desired:
            _make_directories(base, path, manifest)
        installed = _install_hooks(base, expected_files={p: info[1] for p, info in before.items()})
        for path in installed:
            raw, _, mode = _read(path)
            if raw is None or raw != desired[path]:
                raise ValueError("hook_output_changed")
            relative = path.relative_to(base).as_posix()
            old = next((e for e in manifest.files if e.path == relative), None)
            if old is not None or before[path][0] == raw:
                continue
            original, _, old_mode = before[path]
            manifest.files.append(
                InstalledFile(
                    host="claude",
                    path=relative,
                    sha256=_sha(raw),
                    mode=mode,
                    before=base64.b64encode(original).decode() if original is not None else None,
                    before_mode=old_mode,
                    added_keys=["hooks.Stop.ddk"] if path == settings else [],
                )
            )
        write_settings(base / MANIFEST, manifest.model_dump(), identity)
    finally:
        lock.release()
    return installed


def _unlink(path: Path, identity: tuple[int, ...]) -> None:
    with parent_descriptor(path) as (descriptor, name):
        if file_identity(os.stat(name, dir_fd=descriptor, follow_symlinks=False)) != identity:
            raise ValueError("uninstall_file_changed")
        os.unlink(name, dir_fd=descriptor)
        os.fsync(descriptor)


def _uninstall(hosts: list[str], base: Path, *, dry_run: bool = False) -> Record:
    manifest, identity = _manifest(base)
    removed: list[str] = []
    conflicts: list[str] = []
    selected = [entry for entry in manifest.files if entry.host in hosts]
    for entry in selected:
        path = base / entry.path
        try:
            raw, current, _ = _read(path)
            if raw is None or current is None or _sha(raw) != entry.sha256:
                raise ValueError("uninstall_conflict")
            if not dry_run:
                if entry.before is None:
                    _unlink(path, current)
                else:
                    atomic_write(
                        path,
                        base64.b64decode(entry.before, validate=True),
                        mode=entry.before_mode,
                        expected_identity=current,
                    )
                manifest.files.remove(entry)
            removed.append(entry.path)
        except (OSError, ValueError):
            conflicts.append(entry.path)
    if not dry_run and identity is not None:
        if manifest.files:
            write_settings(base / MANIFEST, manifest.model_dump(), identity)
        else:
            _unlink(base / MANIFEST, identity)
    return {
        "status": "blocked" if conflicts else "ok",
        "removed": removed,
        "conflicts": conflicts,
        "dry_run": dry_run,
    }


def uninstall_hosts(hosts: list[str], target_dir: Path, *, dry_run: bool = False) -> Record:
    base = Path(os.path.abspath(target_dir))
    manifest, identity = _manifest(base)
    if dry_run or identity is None:
        return _uninstall(hosts, base, dry_run=True)
    lock = OwnedLock(base / ".ddk/install.lock", str(uuid4())).acquire()
    try:
        result = _uninstall(hosts, base)
    finally:
        lock.release()
    for name in sorted(manifest.directories, key=lambda p: len(Path(p).parts), reverse=True):
        with suppress(OSError), parent_descriptor(base / name) as (descriptor, child):
            os.rmdir(child, dir_fd=descriptor)
    return result


def detect_tools(project_dir: Path | None = None) -> list[str]:
    project = project_dir or Path.cwd()
    home = Path.home()
    return [
        host
        for host in HOSTS
        if any(
            (base / marker).is_dir()
            for base in (project, home)
            for marker in (
                {"copilot": ".github", "opencode": ".config/opencode"}.get(host, f".{host}"),
                f".{host}",
            )
        )
    ]


InstallerFn = Callable[[Path | None], InstallResult]
INSTALLERS: dict[str, InstallerFn] = {name: partial(install_host, name) for name in HOSTS}
install_claude = INSTALLERS["claude"]
install_gemini = INSTALLERS["gemini"]
install_opencode = INSTALLERS["opencode"]
install_codex = INSTALLERS["codex"]
install_copilot = INSTALLERS["copilot"]
install_cursor = INSTALLERS["cursor"]
install_kiro = INSTALLERS["kiro"]


def install_all(target_dir: Path | None = None) -> list[InstallResult]:
    return [install_host(host, target_dir) for host in detect_tools(target_dir)]

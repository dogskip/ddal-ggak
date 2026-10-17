"""Opt-in guards preserve existing settings and refuse unrelated Git hooks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

from ddk.models.verified_change import Record, decode_json, object_record, object_records
from ddk.security.file_access import file_identity, read_regular
from ddk.services.durable_files import OwnedLock, atomic_write, ensure_directory

_GIT_HOOK = (
    b"#!/bin/sh\n# Managed by ddk verified gate v1.\n"
    b'exec ddk change gate --repo "$(git rev-parse --show-toplevel)" --pre-push --json\n'
)
_STOP = 'ddk change gate --repo "${CLAUDE_PROJECT_DIR:-.}" --json >&2 || exit 2'


def read_settings(path: Path) -> tuple[Record, tuple[int, ...] | None]:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {}, None
    value = decode_json(read_regular(path, 2 * 1024**2))
    if file_identity(path.lstat()) != file_identity(info):
        raise ValueError("settings_changed")
    return value, file_identity(info)


def write_settings(path: Path, value: Record, identity: tuple[int, ...] | None) -> None:
    ensure_directory(path.parent)
    payload = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
    atomic_write(path, payload, exclusive=identity is None, expected_identity=identity)


def prepare_hooks(repository: Path) -> tuple[Path, Path, Record, tuple[int, ...] | None]:
    repository = repository.resolve()
    query = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "core.fsmonitor=false",
            "config",
            "--get",
            "core.hooksPath",
        ],
        capture_output=True,
        timeout=5,
        check=False,
    )
    if query.returncode != 1:
        raise ValueError("external_hooks_path")
    metadata = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "core.fsmonitor=false",
            "--no-replace-objects",
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "hooks",
        ],
        capture_output=True,
        timeout=5,
        check=True,
    )
    if len(metadata.stdout) > 16384:
        raise ValueError("git_metadata_limit")
    directory = Path(metadata.stdout.decode().strip())
    path = directory / "pre-push"
    if (path.exists() or path.is_symlink()) and read_regular(path, 65536) != _GIT_HOOK:
        raise ValueError("hook_conflict")
    settings = repository / ".claude/settings.json"
    config, identity = read_settings(settings)
    hooks = object_record(config.setdefault("hooks", {}))
    groups = object_records(hooks.setdefault("Stop", []))
    for group in groups:
        object_records(group.get("hooks"))
    if not any(
        hook.get("command") == _STOP for group in groups for hook in object_records(group["hooks"])
    ):
        groups.append({"hooks": [{"type": "command", "command": _STOP, "timeout": 60}]})
    hooks["Stop"] = groups
    return path, settings, config, identity


def git_hook_bytes() -> bytes:
    return _GIT_HOOK


def install_hooks(
    repository: Path, *, expected_files: dict[Path, tuple[int, ...] | None] | None = None
) -> list[Path]:
    path, _, _, _ = prepare_hooks(repository)
    ensure_directory(path.parent)
    lock = OwnedLock(path.parent / "ddk-gate.lock", str(uuid4())).acquire()
    try:
        path, settings, config, identity = prepare_hooks(repository)
        for target, expected in (expected_files or {}).items():
            try:
                observed = file_identity(target.lstat())
            except FileNotFoundError:
                observed = None
            if observed != expected:
                raise ValueError("hook_input_changed")
        if not path.exists():
            atomic_write(path, _GIT_HOOK, mode=0o755, exclusive=True)
        elif path.stat().st_mode & 0o777 != 0o755:
            atomic_write(path, _GIT_HOOK, mode=0o755, expected_identity=file_identity(path.lstat()))
        if (
            identity is None
            or read_regular(settings, 2 * 1024**2)
            != (json.dumps(config, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode()
        ):
            write_settings(settings, config, identity)
    finally:
        lock.release()
    return [path, settings]

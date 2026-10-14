"""Observed local prerequisites shared by bootstrap, doctor and browser probing."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

from playwright.async_api import async_playwright

from ddk.models.verified_change import Record, record_digest
from ddk.security.file_access import file_identity, parent_descriptor


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with parent_descriptor(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("regular_file_required")
        while block := source.read(1024**2):
            digest.update(block)
        if file_identity(before) != file_identity(os.fstat(source.fileno())):
            raise ValueError("observed_file_changed")
    return digest.hexdigest()


def host_fonts() -> str:
    if platform.system() == "Linux" and shutil.which("fc-list"):
        from ddk.adapters.verified_worker import font_manifest

        return font_manifest()
    paths = (
        [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
        if platform.system() == "Darwin"
        else [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    )
    rows: list[Record] = []
    total = 0
    for base in paths:
        if not base.is_dir():
            continue
        for file in sorted(base.rglob("*")):
            if (
                file.suffix.lower() not in {".ttf", ".otf", ".ttc", ".dfont"}
                or file.is_symlink()
                or not file.is_file()
            ):
                continue
            total += file.stat().st_size
            if len(rows) >= 4000 or total > 1024**3:
                raise ValueError("font_manifest_limit")
            rows.append(
                {
                    "directory": str(base),
                    "path": str(file.relative_to(base)),
                    "sha256": file_sha256(file),
                }
            )
    if not rows:
        raise ValueError("font_manifest_unavailable")
    return record_digest(rows)


def tool_version(argv: list[str]) -> str | None:
    if not shutil.which(argv[0]):
        return None
    try:
        result = subprocess.run(argv, capture_output=True, timeout=5, check=False)
        return (
            result.stdout.decode(errors="replace").strip()[:256] if result.returncode == 0 else None
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


async def observe_environment(repository: Path) -> tuple[Record, str]:
    async with async_playwright() as p:
        binary = Path(p.chromium.executable_path)
        if not binary.is_file():
            build = next((p for p in binary.parents if p.name.startswith("chromium-")), None)
            candidates = (
                sorted(build.parent.glob("chromium_headless_shell-*/**/chrome-headless-shell"))
                if build is not None
                else []
            )
            if not candidates:
                raise ValueError("chromium_unavailable")
            binary = candidates[-1]
        binary = binary.resolve(strict=True)
        browser = await p.chromium.launch(
            headless=True, chromium_sandbox=True, executable_path=str(binary), timeout=10000
        )
        try:
            browser_version = browser.version
        finally:
            await browser.close()
    locks = [
        {"path": name, "sha256": file_sha256(repository / name)}
        for name in (
            "uv.lock",
            "poetry.lock",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
        )
        if (repository / name).is_file()
    ]
    node = tool_version(["node", "--version"])
    env: Record = {
        "record_type": "environment",
        "schema_version": "verified-change/1",
        "assurance": "trusted-local",
        "os_name": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
        "runtime_name": "host",
        "runtime_version": platform.python_version(),
        "python_version": platform.python_version(),
        "node_version": node or "unavailable",
        "package_manager": "not-used",
        "package_manager_version": "not-used",
        "playwright_version": version("playwright"),
        "browser_version": browser_version,
        "locale": "en-US",
        "timezone": "UTC",
        "app_image_sha256": None,
        "checker_image_sha256": None,
        "lockfile_sha256": record_digest(locks),
        "browser_binary_sha256": file_sha256(binary),
        "fixture_sha256": record_digest([]),
        "font_manifest_sha256": host_fonts(),
        "policy_sha256": record_digest(
            {"network": "same-origin", "headless": True, "chromium_sandbox": True}
        ),
        "endpoint_kind": "local",
    }
    return env, str(binary)


async def readiness(repository: Path) -> Record:
    checks: list[Record] = []
    for name, argv, required in [
        ("python", [sys.executable, "--version"], True),
        ("git", ["git", "--version"], True),
        ("node", ["node", "--version"], False),
        ("docker", ["docker", "version", "--format", "{{.Server.Version}}"], False),
        ("claude-cli", ["claude", "--version"], False),
        ("codex-cli", ["codex", "--version"], False),
    ]:
        observed = tool_version(argv)
        if name == "python" and sys.version_info < (3, 12):
            observed = None
        checks.append(
            {
                "name": name,
                "status": "ready" if observed else "blocked" if required else "warning",
                "observed": observed,
                "action": None
                if observed
                else {
                    "python": "uv python install 3.12",
                    "git": "brew install git" if platform.system() == "Darwin" else "git --version",
                    "node": "brew install node"
                    if platform.system() == "Darwin"
                    else "node --version",
                    "docker": "docker info",
                    "claude-cli": "claude --help",
                    "codex-cli": "codex --help",
                }[name],
            }
        )
    git = tool_version(
        ["git", "-c", "core.fsmonitor=false", "-C", str(repository), "status", "--porcelain"]
    )
    checks.append(
        {
            "name": "git-status",
            "status": "ready" if git == "" else "warning",
            "observed": "clean" if git == "" else "changes-or-unavailable",
            "action": None,
        }
    )
    try:
        env, binary = await observe_environment(repository)
        checks.append(
            {
                "name": "chromium",
                "status": "ready",
                "observed": {
                    "path": binary,
                    "sha256": env["browser_binary_sha256"],
                    "font_manifest_sha256": env["font_manifest_sha256"],
                },
                "action": None,
            }
        )
    except Exception as error:
        checks.append(
            {
                "name": "chromium",
                "status": "blocked",
                "observed": type(error).__name__,
                "action": "playwright install chromium",
            }
        )
    try:
        with sqlite3.connect(":memory:") as catalog:
            catalog.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        checks.append(
            {
                "name": "sqlite-fts5",
                "status": "ready",
                "observed": sqlite3.sqlite_version,
                "action": None,
            }
        )
    except sqlite3.Error:
        checks.append(
            {
                "name": "sqlite-fts5",
                "status": "warning",
                "observed": sqlite3.sqlite_version,
                "action": "uv python install 3.12",
            }
        )
    tools = observe_tools(repository)
    checks.append(
        {
            "name": "docker-images",
            "status": "ready" if tools["docker_images"] else "warning",
            "observed": tools["docker_images"],
            "action": None if tools["docker_images"] else "docker image ls --digests",
        }
    )
    keys = {
        key: bool(os.environ.get(key))
        for key in ("ANTHROPIC_API_KEY", "DDK_ANTHROPIC_API_KEY", "OPENAI_API_KEY")
    }
    checks.append(
        {
            "name": "provider-credentials",
            "status": "ready" if any(keys.values()) else "warning",
            "observed": keys,
            "action": None if any(keys.values()) else "export DDK_ANTHROPIC_API_KEY=<approved-key>",
        }
    )
    return {
        "status": "blocked"
        if any(c["status"] == "blocked" for c in checks)
        else "warning"
        if any(c["status"] == "warning" for c in checks)
        else "ready",
        "checks": checks,
        "read_only": True,
    }


def observe_tools(repository: Path) -> Record:
    """Record manifests and existing image digests without installing or running project code."""
    manifests: list[Record] = []
    names = {"pyproject.toml", "package.json", "ddk.toml", ".ddk/verify.toml"}
    names.update(p.name for p in repository.glob("playwright.config.*"))
    for name in sorted(names):
        path = repository / name
        if path.is_file():
            manifests.append({"path": name, "sha256": file_sha256(path)})
    images: list[Record] = []
    docker_status = "unavailable"
    if shutil.which("docker"):
        try:
            with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
                result = subprocess.run(
                    ["docker", "image", "ls", "--no-trunc", "--digests", "--format", "{{json .}}"],
                    stdout=output,
                    stderr=errors,
                    timeout=5,
                    check=False,
                )
                output.seek(0)
                raw = output.read(1024**2 + 1)
                if result.returncode == 0 and len(raw) <= 1024**2:
                    for line in raw.splitlines():
                        row = json.loads(line)
                        images.append(
                            {
                                "id": row.get("ID"),
                                "digest": row.get("Digest"),
                                "repository": row.get("Repository"),
                                "tag": row.get("Tag"),
                            }
                        )
                    docker_status = "observed"
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return {
        "format": "host-tools/1",
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "manifests": manifests,
        "docker_status": docker_status,
        "docker_images": sorted(images, key=lambda row: json.dumps(row, sort_keys=True)),
    }

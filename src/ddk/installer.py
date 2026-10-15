"""Install command assets and MCP settings while preserving unrelated configuration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from ddk.security.file_access import read_regular
from ddk.services.durable_files import atomic_write, ensure_directory
from ddk.services.verified_hooks import install_hooks as install_hooks
from ddk.services.verified_hooks import prepare_hooks as prepare_hooks
from ddk.services.verified_hooks import read_settings, write_settings

# 번들 커맨드 템플릿 디렉토리
_ASSETS_DIR = Path(__file__).parent / "assets" / "commands"

# MCP 서버 stdio 설정
_MCP_STDIO_CONFIG: dict[str, object] = {
    "type": "stdio",
    "command": "ddk",
    "args": ["serve"],
}


@dataclass
class InstallResult:
    """단일 도구 설치 결과."""

    tool: str
    success: bool
    installed_files: list[Path] = field(default_factory=lambda: cast(list[Path], []))
    message: str = ""


# ---------------------------------------------------------------------------
# Per-tool installers
# ---------------------------------------------------------------------------


def install_claude(target_dir: Path | None = None) -> InstallResult:
    """Claude Code에 ddk 슬래시 커맨드 + MCP 서버 등록."""
    project_dir = target_dir or Path.cwd()
    read_settings(project_dir / ".claude/settings.json")
    cmd_dir = project_dir / ".claude" / "commands" / "ddk"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "claude", cmd_dir)

    # MCP 서버 등록
    settings_path = project_dir / ".claude" / "settings.json"
    _register_mcp_claude(settings_path, "ddk", _MCP_STDIO_CONFIG)
    installed.append(settings_path)

    return InstallResult(
        tool="claude", success=True, installed_files=installed, message=str(cmd_dir)
    )


def install_gemini(target_dir: Path | None = None) -> InstallResult:
    """Gemini CLI에 ddk 슬래시 커맨드 설치."""
    project_dir = target_dir or Path.cwd()
    cmd_dir = project_dir / ".gemini" / "commands" / "ddk"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "gemini", cmd_dir)
    return InstallResult(
        tool="gemini", success=True, installed_files=installed, message=str(cmd_dir)
    )


def install_opencode(target_dir: Path | None = None) -> InstallResult:
    """OpenCode에 ddk 슬래시 커맨드 + MCP 서버 등록."""
    project_dir = target_dir or Path.cwd()
    cmd_dir = project_dir / ".opencode" / "commands" / "ddk"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "opencode", cmd_dir)

    # MCP 서버 등록 (opencode config.json 형식)
    config_path = project_dir / ".opencode" / "config.json"
    _register_mcp_opencode(config_path, "ddk", _MCP_STDIO_CONFIG)
    installed.append(config_path)

    return InstallResult(
        tool="opencode", success=True, installed_files=installed, message=str(cmd_dir)
    )


def install_codex(target_dir: Path | None = None) -> InstallResult:
    """OpenAI Codex CLI에 ddk 슬래시 커맨드 설치."""
    project_dir = target_dir or Path.cwd()
    cmd_dir = project_dir / ".codex" / "commands" / "ddk"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "codex", cmd_dir)
    return InstallResult(
        tool="codex", success=True, installed_files=installed, message=str(cmd_dir)
    )


def install_copilot(target_dir: Path | None = None) -> InstallResult:
    """GitHub Copilot에 ddk 커맨드 설치."""
    project_dir = target_dir or Path.cwd()
    # Copilot 커스텀 커맨드는 .github/extensions/ 또는 .github/copilot-instructions.md
    cmd_dir = project_dir / ".github" / "extensions"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "copilot", cmd_dir, prefix="ddk-")
    return InstallResult(
        tool="copilot", success=True, installed_files=installed, message=str(cmd_dir)
    )


def install_cursor(target_dir: Path | None = None) -> InstallResult:
    """Cursor에 ddk 커맨드 규칙 설치."""
    project_dir = target_dir or Path.cwd()
    rules_dir = project_dir / ".cursor" / "rules"
    ensure_directory(rules_dir)

    installed = _copy_commands(_ASSETS_DIR / "cursor", rules_dir)
    return InstallResult(
        tool="cursor", success=True, installed_files=installed, message=str(rules_dir)
    )


def install_kiro(target_dir: Path | None = None) -> InstallResult:
    """Kiro에 ddk 슬래시 커맨드 설치."""
    project_dir = target_dir or Path.cwd()
    cmd_dir = project_dir / ".kiro" / "steering"
    ensure_directory(cmd_dir)

    installed = _copy_commands(_ASSETS_DIR / "kiro", cmd_dir, prefix="ddk-")
    return InstallResult(tool="kiro", success=True, installed_files=installed, message=str(cmd_dir))


# ---------------------------------------------------------------------------
# install_all + registry
# ---------------------------------------------------------------------------

InstallerFn = Callable[[Path | None], InstallResult]

INSTALLERS: dict[str, InstallerFn] = {
    "claude": install_claude,
    "gemini": install_gemini,
    "opencode": install_opencode,
    "codex": install_codex,
    "copilot": install_copilot,
    "cursor": install_cursor,
    "kiro": install_kiro,
}


def install_all(target_dir: Path | None = None) -> list[InstallResult]:
    """지원하는 모든 AI 도구에 설치."""
    results: list[InstallResult] = []
    for name, fn in INSTALLERS.items():
        try:
            results.append(fn(target_dir))
        except Exception as e:  # noqa: BLE001
            results.append(InstallResult(tool=name, success=False, message=str(e)))
    return results


def detect_tools(project_dir: Path | None = None) -> list[str]:
    """현재 환경에서 감지된 AI 도구 목록 반환."""
    home = Path.home()
    project = project_dir or Path.cwd()

    markers: dict[str, list[Path]] = {
        "claude": [home / ".claude", project / ".claude"],
        "gemini": [home / ".gemini", project / ".gemini"],
        "opencode": [home / ".opencode", project / ".opencode"],
        "codex": [home / ".codex", project / ".codex"],
        "copilot": [project / ".github"],
        "cursor": [home / ".cursor", project / ".cursor"],
        "kiro": [home / ".kiro", project / ".kiro"],
    }

    detected: list[str] = []
    for tool, paths in markers.items():
        if any(p.exists() for p in paths):
            detected.append(tool)
    return detected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _copy_commands(src_dir: Path, dst_dir: Path, prefix: str = "") -> list[Path]:
    """src_dir의 *.md 파일을 dst_dir에 복사한다."""
    copied: list[Path] = []
    if not src_dir.exists():
        return copied
    for src_file in src_dir.glob("*.md"):
        dst = dst_dir / f"{prefix}{src_file.name}"
        atomic_write(dst, read_regular(src_file, 2 * 1024**2), mode=0o644)
        copied.append(dst)
    return copied


def _register_mcp_claude(
    settings_path: Path,
    server_name: str,
    server_config: dict[str, object],
) -> None:
    """Claude Code settings.json에 MCP 서버를 등록(없으면 생성)."""
    settings, identity = read_settings(settings_path)
    mcp_servers = settings.setdefault("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        raise ValueError("invalid_mcp_configuration")
    mcp_servers[server_name] = server_config
    write_settings(settings_path, settings, identity)


def _register_mcp_opencode(
    config_path: Path,
    server_name: str,
    server_config: dict[str, object],
) -> None:
    """OpenCode config.json에 MCP 서버를 등록(없으면 생성)."""
    config, identity = read_settings(config_path)
    mcp = config.setdefault("mcp", {})
    if not isinstance(mcp, dict):
        raise ValueError("invalid_mcp_configuration")
    servers = cast(dict[str, object], mcp).setdefault("servers", {})
    if not isinstance(servers, dict):
        raise ValueError("invalid_mcp_configuration")
    cast(dict[str, object], servers)[server_name] = server_config
    write_settings(config_path, config, identity)

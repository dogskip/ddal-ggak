"""Sandbox execution policy definitions — VALID-06.

Defines the security boundary constraints for sandboxed code execution:
- ENV_WHITELIST: environment variables allowed in sandbox
- FORBIDDEN_READ_PATHS: paths that must never be read
- ALLOWED_COMMANDS: commands permitted to run in sandbox
"""

from __future__ import annotations

from pathlib import Path

ENV_WHITELIST: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "TERM",
        "NODE_ENV",
        "npm_config_cache",
        "DDK_SANDBOX_MODE",
        "DDK_LOG_LEVEL",
    }
)

FORBIDDEN_READ_PATHS: frozenset[str] = frozenset(
    {
        "~/.ssh/",
        "~/.aws/",
        "~/.config/gcloud/",
        "~/.gnupg/",
        "/etc/shadow",
        "/etc/passwd",
    }
)

ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        "npm",
        "npx",
        "pnpm",
        "yarn",
        "bun",
        "node",
        "tsc",
        "vite",
        "git",
    }
)


def is_command_allowed(command: str) -> bool:
    """Check if a command is in the allowlist."""
    base_command = command.split("/")[-1].split()[0] if command else ""
    return base_command in ALLOWED_COMMANDS


def is_path_forbidden(path: str | Path) -> bool:
    """Check if a path matches any forbidden read path."""
    resolved = Path(path).expanduser().resolve()
    path_str = str(resolved)
    for forbidden in FORBIDDEN_READ_PATHS:
        forbidden_expanded = str(Path(forbidden).expanduser().resolve())
        if path_str.startswith(forbidden_expanded):
            return True
    return False


def is_env_allowed(var_name: str) -> bool:
    """Check if an environment variable is in the whitelist."""
    return var_name in ENV_WHITELIST

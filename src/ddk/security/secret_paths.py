"""Repo-relative secret-file detection — keep credentials out of LLM context.

``adapters/sandbox/policy.py`` guards *absolute home* paths (``~/.ssh`` …) for
sandbox execution. This module is the complementary guard for the *target repo*:
files inside the repo that must never be read into an LLM prompt (``.env``,
private keys, cloud credentials, …).

Used by ``ContextPackBuilder`` as defense layer 1 (never read the file); inline
secrets that slip through are scrubbed by ``security.redact.redact_string`` as
defense layer 2.
"""

from __future__ import annotations

# Exact secret filenames (case-insensitive).
_SECRET_FILENAMES: frozenset[str] = frozenset(
    {
        ".env",
        ".mcp.json",
        "opencode.json",
        "opencode.jsonc",
        ".npmrc",
        ".netrc",
        ".pgpass",
        ".htpasswd",
        ".dockercfg",
        "credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "secring.gpg",
    }
)

# Secret file suffixes (case-insensitive).
_SECRET_SUFFIXES: tuple[str, ...] = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
    ".jks",
    ".ppk",
    ".asc",
)

# Path components that mark a secret directory anywhere in the path.
_SECRET_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".git",
        ".ddk",
        ".ddk-home",
        ".codex",
        ".config",
        ".claude",
        ".gemini",
        ".opencode",
        ".ssh",
        ".aws",
        ".gnupg",
        ".gcloud",
        "gcloud",
        "secrets",
        ".docker",
    }
)


def is_secret_path(rel_path: str) -> bool:
    """True if *rel_path* (repo-relative) likely contains credentials.

    Private inputs, tool-owned data and every ``.env*`` spelling are excluded.
    This predicate also handles directory entries before a recursive copy.
    """
    norm = rel_path.replace("\\", "/").strip("/")
    if not norm:
        return False
    parts = [part.lower() for part in norm.split("/")]
    if any(
        parts[i : i + 2] in ([".cursor", "mcp.json"], [".vscode", "mcp.json"])
        for i in range(len(parts) - 1)
    ):
        return True
    return any(
        part in _SECRET_DIR_PARTS
        or part in _SECRET_FILENAMES
        or part.startswith(".env")
        or part.endswith(_SECRET_SUFFIXES)
        for part in parts
    )

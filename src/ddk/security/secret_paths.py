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
    {".ssh", ".aws", ".gnupg", ".gcloud", "gcloud", "secrets"}
)

# ``.env.<x>`` variants that are safe templates (committed by convention).
_SAFE_ENV_SUFFIXES: tuple[str, ...] = (
    ".example",
    ".sample",
    ".template",
    ".dist",
    ".defaults",
    ".local.example",
)


def is_secret_path(rel_path: str) -> bool:
    """True if *rel_path* (repo-relative) likely contains credentials.

    Conservative by design: a security guard prefers a false exclusion over
    leaking a secret. Safe ``.env`` templates (``.env.example`` …) are allowed.
    """
    norm = rel_path.replace("\\", "/").strip("/")
    if not norm:
        return False
    parts = norm.split("/")
    name = parts[-1]
    lower = name.lower()

    # Secret directory anywhere in the path (e.g. config/.aws/credentials).
    if any(part.lower() in _SECRET_DIR_PARTS for part in parts[:-1]):
        return True
    # Docker registry auth.
    if ".docker" in parts[:-1] and lower == "config.json":
        return True

    # .env and .env.<env>, but not .env.example / .env.sample / …
    if lower == ".env":
        return True
    if lower.startswith(".env.") and not lower.endswith(_SAFE_ENV_SUFFIXES):
        return True

    if lower in _SECRET_FILENAMES:
        return True
    return lower.endswith(_SECRET_SUFFIXES)

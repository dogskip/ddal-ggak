"""Unit tests for repo-relative secret-path detection."""

from __future__ import annotations

import pytest

from ddk.security.secret_paths import is_secret_path


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        ".env.local",
        "config/.env",
        "apps/web/.env.staging",
        "certs/server.pem",
        "keys/private.key",
        "id_rsa",
        "deploy/id_ed25519",
        ".npmrc",
        ".netrc",
        ".aws/credentials",
        "home/.aws/credentials",
        ".ssh/id_rsa",
        ".docker/config.json",
        "secrets/token.txt",
        "store.p12",
        "cert.pfx",
    ],
)
def test_secret_paths_detected(path: str) -> None:
    assert is_secret_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "src/App.tsx",
        "package.json",
        "README.md",
        "tsconfig.json",
        ".env.example",
        ".env.sample",
        ".env.template",
        "config.json",  # only secret under .docker/
        "docs/keynote.md",  # contains 'key' but not a key file
        "",
    ],
)
def test_non_secret_paths_allowed(path: str) -> None:
    assert is_secret_path(path) is False


def test_backslash_paths_normalized() -> None:
    assert is_secret_path("config\\.aws\\credentials") is True


def test_secret_directory_matching_is_case_insensitive() -> None:
    assert is_secret_path("config/.AWS/credentials") is True

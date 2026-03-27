"""Tests for sandbox execution policy — VALID-06."""

from ddk.adapters.sandbox.policy import (
    ALLOWED_COMMANDS,
    ENV_WHITELIST,
    FORBIDDEN_READ_PATHS,
    is_command_allowed,
    is_env_allowed,
    is_path_forbidden,
)


class TestEnvWhitelist:
    def test_contains_path(self):
        assert "PATH" in ENV_WHITELIST

    def test_contains_home(self):
        assert "HOME" in ENV_WHITELIST

    def test_contains_node_env(self):
        assert "NODE_ENV" in ENV_WHITELIST

    def test_contains_ddk_vars(self):
        assert "DDK_SANDBOX_MODE" in ENV_WHITELIST
        assert "DDK_LOG_LEVEL" in ENV_WHITELIST

    def test_rejects_unknown(self):
        assert "MALICIOUS_VAR" not in ENV_WHITELIST

    def test_is_frozenset(self):
        assert isinstance(ENV_WHITELIST, frozenset)


class TestForbiddenPaths:
    def test_contains_ssh(self):
        assert "~/.ssh/" in FORBIDDEN_READ_PATHS

    def test_contains_aws(self):
        assert "~/.aws/" in FORBIDDEN_READ_PATHS

    def test_contains_gcloud(self):
        assert "~/.config/gcloud/" in FORBIDDEN_READ_PATHS

    def test_contains_gnupg(self):
        assert "~/.gnupg/" in FORBIDDEN_READ_PATHS


class TestAllowedCommands:
    def test_contains_npm(self):
        assert "npm" in ALLOWED_COMMANDS

    def test_contains_node(self):
        assert "node" in ALLOWED_COMMANDS

    def test_contains_git(self):
        assert "git" in ALLOWED_COMMANDS

    def test_contains_tsc(self):
        assert "tsc" in ALLOWED_COMMANDS


class TestIsCommandAllowed:
    def test_allowed_command(self):
        assert is_command_allowed("npm") is True

    def test_disallowed_command(self):
        assert is_command_allowed("rm") is False

    def test_full_path_command(self):
        assert is_command_allowed("/usr/bin/node") is True

    def test_empty_command(self):
        assert is_command_allowed("") is False


class TestIsPathForbidden:
    def test_ssh_forbidden(self):
        assert is_path_forbidden("~/.ssh/id_rsa") is True

    def test_normal_path_allowed(self):
        assert is_path_forbidden("/tmp/work/file.txt") is False


class TestIsEnvAllowed:
    def test_allowed(self):
        assert is_env_allowed("PATH") is True

    def test_disallowed(self):
        assert is_env_allowed("SECRET_KEY") is False

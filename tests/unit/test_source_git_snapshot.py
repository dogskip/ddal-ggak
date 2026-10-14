from __future__ import annotations

import subprocess

import pytest

from ddk.services.source_snapshot import capture_git_source, capture_git_worktree


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout


def test_git_capture_includes_untracked_and_deletions_without_running_hooks(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.py").write_text("before\n")
    git(tmp_path, "add", "a.py")
    git(tmp_path, "commit", "-qm", "initial")
    base = capture_git_source(tmp_path, "HEAD")
    (tmp_path / "a.py").unlink()
    (tmp_path / "new.py").write_text("after\n")
    (tmp_path / ".env").write_text("secret")
    candidate = capture_git_worktree(tmp_path)
    assert [f.path for f in base.files] == ["a.py"]
    assert [f.path for f in candidate.files] == ["new.py"]
    assert base.tree_sha256 != candidate.tree_sha256


def test_git_ref_rejects_options_and_link_files(tmp_path):
    git(tmp_path, "init", "-q")
    with pytest.raises(ValueError):
        capture_git_source(tmp_path, "--help")

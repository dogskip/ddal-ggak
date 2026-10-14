"""Rollback must never destroy untracked user files or the ``.ddk/`` workspace."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ddk.adapters.local_git import LocalGitAdapter
from ddk.exceptions import DirtyWorkingTreeError

_REF = "refs/ddk/test/checkpoint"


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for args in (
        ["init"],
        ["config", "user.email", "test@test.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=repo, capture_output=True, check=True)
    (repo / "file.txt").write_text("initial")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


async def _checkpoint(repo: Path) -> LocalGitAdapter:
    adapter = LocalGitAdapter()
    await adapter.create_checkpoint(repo, _REF)
    return adapter


def _seed_workspace(repo: Path) -> Path:
    report = repo / ".ddk" / "cases" / "C-001" / "reports" / "scorecard.json"
    report.parent.mkdir(parents=True)
    report.write_text("{}")
    return report


class TestUntrackedFilesAreProtected:
    async def test_untracked_file_blocks_rollback_without_force(self, git_repo: Path) -> None:
        adapter = await _checkpoint(git_repo)
        draft = git_repo / "my-draft.md"
        draft.write_text("작성 중인 문서")

        with pytest.raises(DirtyWorkingTreeError) as exc_info:
            await adapter.rollback_to(git_repo, _REF)

        assert exc_info.value.untracked == ["my-draft.md"]
        assert "my-draft.md" in str(exc_info.value)
        assert draft.read_text() == "작성 중인 문서"

    async def test_force_still_removes_untracked_files(self, git_repo: Path) -> None:
        adapter = await _checkpoint(git_repo)
        generated = git_repo / "generated.ts"
        generated.write_text("export {}")

        await adapter.rollback_to(git_repo, _REF, force=True)

        assert not generated.exists()


class TestWorkspaceIsNeverDeleted:
    async def test_ddk_workspace_alone_does_not_block_rollback(self, git_repo: Path) -> None:
        adapter = await _checkpoint(git_repo)
        report = _seed_workspace(git_repo)

        await adapter.rollback_to(git_repo, _REF)

        assert report.exists()

    async def test_force_rollback_keeps_ddk_workspace(self, git_repo: Path) -> None:
        adapter = await _checkpoint(git_repo)
        report = _seed_workspace(git_repo)
        (git_repo / "generated.ts").write_text("export {}")

        await adapter.rollback_to(git_repo, _REF, force=True)

        assert report.exists()
        assert not (git_repo / "generated.ts").exists()

    async def test_tracked_edit_is_reverted_on_force(self, git_repo: Path) -> None:
        adapter = await _checkpoint(git_repo)
        (git_repo / "file.txt").write_text("edited")

        with pytest.raises(DirtyWorkingTreeError):
            await adapter.rollback_to(git_repo, _REF)
        await adapter.rollback_to(git_repo, _REF, force=True)

        assert (git_repo / "file.txt").read_text() == "initial"


class TestDirtyWorkingTreeErrorShape:
    def test_untracked_defaults_to_empty_for_existing_callers(self) -> None:
        err = DirtyWorkingTreeError(repo_path="/r", modified=["a"], staged=[])

        assert err.untracked == []

    def test_message_lists_untracked_files(self) -> None:
        err = DirtyWorkingTreeError(repo_path="/r", modified=[], staged=[], untracked=["new.ts"])

        assert "new.ts" in str(err)

"""Tests for LocalGitAdapter."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.adapters.local_git import LocalGitAdapter


class TestLocalGitAdapter:
    def test_create_no_args(self) -> None:
        adapter = LocalGitAdapter()
        assert adapter is not None

    def test_status(self) -> None:
        with patch("ddk.adapters.local_git.Repo") as mock_repo_cls:
            mock_diff_item = MagicMock()
            mock_diff_item.a_path = "changed.py"
            mock_repo = MagicMock()
            mock_repo.index.diff.side_effect = [
                [mock_diff_item],  # diff(None) → modified
                [],  # diff("HEAD") → staged
            ]
            mock_repo.untracked_files = ["newfile.txt"]
            mock_repo_cls.return_value = mock_repo

            adapter = LocalGitAdapter()
            status = adapter.status(repo_path=Path("/tmp/repo"))

        assert "changed.py" in status["modified"]
        assert "newfile.txt" in status["untracked"]

    def test_diff(self) -> None:
        with patch("ddk.adapters.local_git.Repo") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.git.diff.return_value = "diff output"
            mock_repo_cls.return_value = mock_repo

            adapter = LocalGitAdapter()
            result = adapter.diff(repo_path=Path("/tmp/repo"))

        assert result == "diff output"

    def test_log(self) -> None:
        with patch("ddk.adapters.local_git.Repo") as mock_repo_cls:
            mock_commit = MagicMock()
            mock_commit.hexsha = "abc123"
            mock_commit.message = "initial commit"
            mock_repo = MagicMock()
            mock_repo.iter_commits.return_value = [mock_commit]
            mock_repo_cls.return_value = mock_repo

            adapter = LocalGitAdapter()
            result = adapter.log(repo_path=Path("/tmp/repo"), max_count=1)

        assert len(result) == 1
        assert result[0]["hexsha"] == "abc123"

    @pytest.mark.asyncio
    async def test_create_checkpoint(self) -> None:
        adapter = LocalGitAdapter()

        with patch.object(adapter, "_run_git", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = "abc123\n"
            sha = await adapter.create_checkpoint(
                repo_path=Path("/tmp/repo"), ref_name="refs/ddk/test"
            )

        assert sha == "abc123"

    @pytest.mark.asyncio
    async def test_rollback_to_dirty_tree_raises(self) -> None:
        adapter = LocalGitAdapter()

        with (
            patch.object(adapter, "_run_git", new_callable=AsyncMock) as run_git,
            patch.object(
                adapter,
                "status",
                return_value={
                    "modified": ["dirty.py"],
                    "staged": [],
                    "untracked": [],
                },
            ),
            pytest.raises(ValueError, match="rollback_disabled"),
        ):
            await adapter.rollback_to(repo_path=Path("/tmp/repo"), ref_name="refs/ddk/test")
        run_git.assert_not_awaited()

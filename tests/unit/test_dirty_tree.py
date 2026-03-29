"""Unit tests for dirty-working-tree protection in rollback."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.exceptions import DirtyWorkingTreeError
from tests.fakes.fake_rollback import FakeRollbackController


@pytest.fixture
def repo() -> Path:
    return Path("/fake/repo")


@pytest.fixture
def ctrl() -> FakeRollbackController:
    c = FakeRollbackController()
    return c


async def _with_checkpoint(ctrl: FakeRollbackController, repo: Path) -> str:
    return await ctrl.create_checkpoint(repo, "ddk/v1")


class TestDirtyTreeProtection:
    async def test_rollback_raises_on_dirty_tree_by_default(
        self, ctrl: FakeRollbackController, repo: Path
    ) -> None:
        await _with_checkpoint(ctrl, repo)
        ctrl.dirty = True
        with pytest.raises(DirtyWorkingTreeError):
            await ctrl.rollback_to(repo, "ddk/v1")

    async def test_rollback_force_proceeds_with_dirty_tree(
        self, ctrl: FakeRollbackController, repo: Path
    ) -> None:
        await _with_checkpoint(ctrl, repo)
        ctrl.dirty = True
        await ctrl.rollback_to(repo, "ddk/v1", force=True)
        assert ctrl.rollback_log[-1]["force"] is True

    async def test_rollback_clean_tree_succeeds_without_force(
        self, ctrl: FakeRollbackController, repo: Path
    ) -> None:
        await _with_checkpoint(ctrl, repo)
        ctrl.dirty = False
        await ctrl.rollback_to(repo, "ddk/v1")
        assert ctrl.rollback_log[-1]["ref_name"] == "ddk/v1"

    async def test_dirty_tree_error_message_contains_modified_files(
        self, ctrl: FakeRollbackController, repo: Path
    ) -> None:
        await _with_checkpoint(ctrl, repo)
        ctrl.dirty = True
        with pytest.raises(DirtyWorkingTreeError) as exc_info:
            await ctrl.rollback_to(repo, "ddk/v1")
        assert "fake_modified_file.py" in str(exc_info.value)

    async def test_rollback_missing_checkpoint_raises_value_error(
        self, ctrl: FakeRollbackController, repo: Path
    ) -> None:
        with pytest.raises(ValueError, match="Checkpoint not found"):
            await ctrl.rollback_to(repo, "ddk/nonexistent")

"""Unit tests for RollbackController — VALID-07.

TDD RED phase: tests written before implementation.
4 tests covering checkpoint creation, rollback, ref format, and error propagation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.services.rollback_controller import RollbackController
from tests.fakes import FakeRollbackController as FakeGitAdapter

# asyncio_mode = "auto" in pyproject.toml — no @pytest.mark.asyncio needed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_controller(fake: FakeGitAdapter) -> RollbackController:
    """Wrap FakeGitAdapter in a real RollbackController."""
    return RollbackController(git=fake, repo_path=Path("/tmp/repo"))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCheckpointCreation:
    async def test_create_checkpoint_returns_commit_hash(self) -> None:
        fake = FakeGitAdapter()
        ctrl = _make_controller(fake)

        result = await ctrl.create_checkpoint(case_id="abc-123", attempt_number=1)

        assert isinstance(result, str)
        assert len(result) > 0  # non-empty commit hash

    async def test_create_checkpoint_stores_ref_in_git(self) -> None:
        fake = FakeGitAdapter()
        ctrl = _make_controller(fake)

        await ctrl.create_checkpoint(case_id="abc-123", attempt_number=2)

        expected_ref = "refs/ddk/fix/abc-123/attempt-2"
        assert expected_ref in fake.checkpoints


class TestRollback:
    async def test_rollback_to_latest_uses_correct_ref(self) -> None:
        fake = FakeGitAdapter()
        ctrl = _make_controller(fake)

        await ctrl.create_checkpoint(case_id="case-xyz", attempt_number=3)
        await ctrl.rollback_to_latest(case_id="case-xyz", attempt_number=3)

        assert len(fake.rollback_log) == 1
        assert fake.rollback_log[0]["ref_name"] == "refs/ddk/fix/case-xyz/attempt-3"

    async def test_rollback_missing_checkpoint_raises_value_error(self) -> None:
        fake = FakeGitAdapter()
        ctrl = _make_controller(fake)

        with pytest.raises(ValueError, match="Checkpoint not found"):
            await ctrl.rollback_to_latest(case_id="no-such-case", attempt_number=99)


class TestRefFormat:
    def test_ref_format_is_correct(self) -> None:
        """Ref name must exactly match refs/ddk/fix/{case_id}/attempt-{n}."""
        fake = FakeGitAdapter()
        ctrl = _make_controller(fake)

        ref = ctrl._ref_name(case_id="abc-123", attempt_number=2)
        assert ref == "refs/ddk/fix/abc-123/attempt-2"

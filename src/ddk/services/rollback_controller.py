"""RollbackController — git checkpoint management for auto-fix attempts. VALID-07.

Thin wrapper around GitAdapter — zero subprocess logic here.
Ref format: refs/ddk/fix/{case_id}/attempt-{n}
"""

from __future__ import annotations

from pathlib import Path

from ddk.adapters.git import GitAdapter


class RollbackController:
    """Manages git checkpoint refs for each auto-fix attempt.

    Each fix attempt gets a stable ref: ``refs/ddk/fix/{case_id}/attempt-{n}``.
    Delegates all git operations to the injected GitAdapter (no direct subprocess).

    Args:
        git: GitAdapter implementation (real or fake for tests).
        repo_path: Absolute path to the repository root.
    """

    def __init__(self, git: GitAdapter, repo_path: Path) -> None:
        self.git = git
        self.repo_path = repo_path

    def _ref_name(self, case_id: str, attempt_number: int) -> str:
        """Return the canonical git ref name for an attempt.

        Args:
            case_id: Unique case identifier.
            attempt_number: 1-based fix attempt number.

        Returns:
            Git ref string in the format ``refs/ddk/fix/{case_id}/attempt-{n}``.
        """
        return f"refs/ddk/fix/{case_id}/attempt-{attempt_number}"

    async def create_checkpoint(self, case_id: str, attempt_number: int) -> str:
        """Create a git ref checkpoint before applying a fix.

        Args:
            case_id: Unique case identifier.
            attempt_number: Fix attempt number (used in ref name).

        Returns:
            Commit hash string from the underlying GitAdapter.
        """
        ref = self._ref_name(case_id, attempt_number)
        return await self.git.create_checkpoint(self.repo_path, ref)

    async def rollback_to_latest(
        self, case_id: str, attempt_number: int, *, force: bool = False
    ) -> None:
        """Roll back the repo to the checkpoint for this attempt number.

        Args:
            case_id: Unique case identifier.
            attempt_number: Attempt number whose checkpoint to restore.
            force: Pass ``True`` to discard uncommitted changes silently.

        Raises:
            ValueError: If the checkpoint ref does not exist (propagated from GitAdapter).
            DirtyWorkingTreeError: If the tree is dirty and ``force`` is ``False``.
        """
        ref = self._ref_name(case_id, attempt_number)
        await self.git.rollback_to(self.repo_path, ref, force=force)

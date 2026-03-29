"""FakeRollbackController — in-memory checkpoint/rollback history."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ddk.exceptions import DirtyWorkingTreeError


class FakeRollbackController:
    """In-memory checkpoint/rollback history."""

    def __init__(self) -> None:
        self.checkpoints: dict[str, str] = {}
        self.rollback_log: list[dict[str, Any]] = []
        self.dirty: bool = False  # set True in tests to simulate a dirty working tree

    async def create_checkpoint(self, repo_path: Path, ref_name: str) -> str:
        commit_hash = f"fake-{len(self.checkpoints):04d}"
        self.checkpoints[ref_name] = commit_hash
        return commit_hash

    async def rollback_to(self, repo_path: Path, ref_name: str, *, force: bool = False) -> None:
        if ref_name not in self.checkpoints:
            raise ValueError(f"Checkpoint not found: {ref_name}")
        if self.dirty and not force:
            raise DirtyWorkingTreeError(
                repo_path=repo_path,
                modified=["fake_modified_file.py"],
                staged=[],
            )
        self.rollback_log.append(
            {"ref_name": ref_name, "commit": self.checkpoints[ref_name], "force": force}
        )

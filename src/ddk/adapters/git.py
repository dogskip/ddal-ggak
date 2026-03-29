"""Git adapter Protocol (hybrid approach per D-04)."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class GitAdapter(Protocol):
    """Protocol for Git operations.

    Read operations use GitPython in real impl.
    Write operations use subprocess in real impl (per D-04).
    """

    # Read operations (GitPython in real impl)
    def status(self, repo_path: Path) -> dict[str, list[str]]: ...

    def diff(self, repo_path: Path, ref: str | None = None) -> str: ...

    def log(
        self, repo_path: Path, max_count: int = 10
    ) -> list[dict[str, str]]: ...

    # Write operations (subprocess in real impl per D-04)
    async def create_worktree(
        self, repo_path: Path, worktree_path: Path, branch: str
    ) -> None: ...

    async def remove_worktree(
        self, repo_path: Path, worktree_path: Path
    ) -> None: ...

    async def create_checkpoint(
        self, repo_path: Path, ref_name: str
    ) -> str: ...

    async def rollback_to(
        self, repo_path: Path, ref_name: str, *, force: bool = False
    ) -> None: ...

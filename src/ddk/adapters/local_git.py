"""Local Git adapter implementation following the hybrid D-04 approach."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

from git import Repo


class LocalGitAdapter:
    """Git adapter using GitPython for reads and subprocess for writes."""

    def status(self, repo_path: Path) -> dict[str, list[str]]:
        """Return a compact working-tree summary for the repository."""
        repo = Repo(repo_path)
        modified = [
            str(item.a_path)
            for item in cast(list[Any], list(repo.index.diff(None)))
            if getattr(item, "a_path", None) is not None
        ]
        staged = [
            str(item.a_path)
            for item in cast(list[Any], list(repo.index.diff("HEAD")))
            if getattr(item, "a_path", None) is not None
        ]
        untracked = list(repo.untracked_files)
        return {
            "modified": sorted(modified),
            "staged": sorted(staged),
            "untracked": sorted(untracked),
        }

    def diff(self, repo_path: Path, ref: str | None = None) -> str:
        """Return a diff string for the repository."""
        repo = Repo(repo_path)
        return repo.git.diff(ref) if ref is not None else repo.git.diff()

    def log(self, repo_path: Path, max_count: int = 10) -> list[dict[str, str]]:
        """Return recent commits as structured dictionaries."""
        repo = Repo(repo_path)
        return [
            {"hexsha": commit.hexsha, "message": commit.message.strip()}
            for commit in cast(list[Any], list(repo.iter_commits(max_count=max_count)))
        ]

    async def create_worktree(self, repo_path: Path, worktree_path: Path, branch: str) -> None:
        """Create a git worktree using subprocess commands."""
        await self._run_git(
            repo_path,
            "worktree",
            "add",
            "-B",
            branch,
            str(worktree_path),
        )

    async def remove_worktree(self, repo_path: Path, worktree_path: Path) -> None:
        """Remove a git worktree using subprocess commands."""
        await self._run_git(repo_path, "worktree", "remove", "--force", str(worktree_path))

    async def create_checkpoint(self, repo_path: Path, ref_name: str) -> str:
        """Create a durable git ref for the current HEAD."""
        head_sha = (await self._run_git(repo_path, "rev-parse", "HEAD")).strip()
        await self._run_git(repo_path, "update-ref", ref_name, head_sha)
        return head_sha

    async def rollback_to(self, repo_path: Path, ref_name: str) -> None:
        """Reset the repository to the given checkpoint ref."""
        await self._run_git(repo_path, "rev-parse", "--verify", ref_name)
        await self._run_git(repo_path, "reset", "--hard", ref_name)

    async def _run_git(self, repo_path: Path, *args: str) -> str:
        """Execute a git subprocess command and return stdout."""
        process = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(repo_path),
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            message = stderr.decode().strip() or stdout.decode().strip()
            raise ValueError(message or f"git {' '.join(args)} failed")
        return stdout.decode()

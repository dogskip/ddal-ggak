"""ArtifactApplier — copy the files of a finished case into the repository, safely.

A file is written only when the repository still holds the version the run started from
(or nothing yet); anything edited since is reported as a conflict, and a replaced file is
kept in a backup folder.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.security.repo_paths import UnsafeRepositoryPathError, resolve_within_repository
from ddk.security.secret_paths import is_secret_path
from ddk.services.file_blocks import is_protected_path

Action = Literal["create", "update", "unchanged", "conflict", "rejected"]


@dataclass(frozen=True)
class FileChange:
    """What applying one generated file would do."""

    path: str
    action: Action
    content: str
    reason: str = ""


class ArtifactApplier:
    """Plans and performs the copy of generated files into a repository."""

    def plan(self, artifacts: GeneratedArtifactSet, repo_root: Path) -> list[FileChange]:
        return [self._plan_file(generated, repo_root) for generated in artifacts.files]

    def write(
        self,
        changes: list[FileChange],
        repo_root: Path,
        *,
        force: bool = False,
        backup_dir: Path | None = None,
    ) -> list[FileChange]:
        """Write creates and updates (and conflicts when ``force``); return what was written."""
        written: list[FileChange] = []
        for change in changes:
            if change.action in {"unchanged", "rejected"}:
                continue
            if change.action == "conflict" and not force:
                continue
            target = resolve_within_repository(repo_root, change.path)
            if backup_dir is not None and target.is_file():
                saved = resolve_within_repository(backup_dir, change.path)
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(target.read_bytes())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")
            written.append(change)
        return written

    def _plan_file(self, generated: GeneratedFile, repo_root: Path) -> FileChange:
        path, content = generated.path, generated.content
        if is_secret_path(path) or is_protected_path(path):
            return FileChange(path, "rejected", content, "secret or tool configuration file")
        try:
            target = resolve_within_repository(repo_root, path)
        except UnsafeRepositoryPathError as exc:
            return FileChange(path, "rejected", content, str(exc))
        if not target.exists():
            return FileChange(path, "create", content)
        try:
            current = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return FileChange(path, "conflict", content, "existing file is not readable text")
        if current == content:
            return FileChange(path, "unchanged", content)
        if not generated.is_new and current == generated.original_content:
            return FileChange(path, "update", content)
        return FileChange(path, "conflict", content, "changed in the repository since the run")

"""Bounded source captures with stable file lists and verified exact bytes."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from ddk.models.verified_change import canonical_json, safe_path
from ddk.security.file_access import file_identity, parent_descriptor, read_regular
from ddk.security.repo_paths import (
    ensure_distinct_paths,
    normalize_repo_relative_path,
    normalize_source_path,
)


class SnapshotError(ValueError):
    """A source capture cannot satisfy its safety or resource contract."""


class SnapshotChangedError(SnapshotError):
    """The source changed before the capture could be sealed."""


class SnapshotCancelledError(SnapshotError):
    """The owner stopped a capture before it completed."""


@dataclass(frozen=True)
class SnapshotFile:
    path: str
    content: bytes
    sha256: str
    mode: int
    size_bytes: int
    identity: tuple[int, ...] = ()

    def manifest_entry(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "mode": self.mode,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class SourceSnapshot:
    files: tuple[SnapshotFile, ...]
    tree_sha256: str


def manifest_digest(files: Iterable[SnapshotFile]) -> str:
    ordered = sorted(files, key=lambda item: item.path.encode("utf-8"))
    ensure_distinct_paths([item.path for item in ordered])
    return hashlib.sha256(canonical_json([item.manifest_entry() for item in ordered])).hexdigest()


def capture_source(
    root: Path,
    *,
    max_file_bytes: int = 2 * 1024 * 1024,
    max_total_bytes: int = 200 * 1024 * 1024,
    max_depth: int = 32,
    max_files: int = 10000,
    cancelled: Callable[[], bool] | None = None,
) -> SourceSnapshot:
    """Capture permitted files and reject changes across two complete passes."""
    if min(max_file_bytes, max_total_bytes, max_depth, max_files) < 0:
        raise SnapshotError("invalid_snapshot_limit")
    root = Path(os.path.abspath(root))
    try:
        normalize_source_path(root.name)
    except ValueError as error:
        raise SnapshotError("protected_snapshot_root") from error

    def checkpoint() -> None:
        if cancelled is not None and cancelled():
            raise SnapshotCancelledError("snapshot_cancelled")

    def inventory() -> tuple[dict[str, tuple[int, ...]], dict[str, tuple[int, ...]]]:
        folders: dict[str, tuple[int, ...]] = {}
        entries: dict[str, tuple[int, ...]] = {}
        total = 0

        def walk(descriptor: int, prefix: str, depth: int) -> None:
            nonlocal total
            checkpoint()
            if depth > max_depth:
                raise SnapshotError("snapshot_depth_limit")
            folders[prefix] = file_identity(os.fstat(descriptor))
            if len(folders) > max_files + 1:
                raise SnapshotError("snapshot_directory_count_limit")
            with os.scandir(descriptor) as children:
                for child in children:
                    checkpoint()
                    relative = prefix + "/" + child.name if prefix else child.name
                    normalize_repo_relative_path(relative)
                    try:
                        normalize_source_path(relative)
                    except ValueError:
                        continue
                    if not safe_path(relative):
                        raise SnapshotError("unsafe_snapshot_path")
                    value = child.stat(follow_symlinks=False)
                    if stat.S_ISDIR(value.st_mode):
                        following = os.open(
                            child.name,
                            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor,
                        )
                        try:
                            walk(following, relative, depth + 1)
                        finally:
                            os.close(following)
                    elif stat.S_ISREG(value.st_mode) and value.st_nlink == 1:
                        if value.st_size > max_file_bytes:
                            raise SnapshotError("snapshot_file_size_limit")
                        entries[relative] = file_identity(value)
                        total += value.st_size
                        if total > max_total_bytes:
                            raise SnapshotError("snapshot_total_size_limit")
                        if len(entries) > max_files:
                            raise SnapshotError("snapshot_file_count_limit")
                    else:
                        raise SnapshotError("snapshot_regular_file_required")

        with parent_descriptor(root / ".capture") as (descriptor, _):
            walk(descriptor, "", 0)
        ensure_distinct_paths(list(entries) + list(folders))
        return entries, folders

    try:
        checkpoint()
        before, folders = inventory()
        captured: list[SnapshotFile] = []
        for relative in sorted(before, key=lambda value: value.encode("utf-8")):
            checkpoint()
            path = root / relative
            if file_identity(path.lstat()) != before[relative]:
                raise SnapshotChangedError("snapshot_changed:" + relative)
            content = read_regular(path, max_file_bytes)
            value = path.lstat()
            if file_identity(value) != before[relative]:
                raise SnapshotChangedError("snapshot_changed:" + relative)
            captured.append(
                SnapshotFile(
                    relative,
                    content,
                    hashlib.sha256(content).hexdigest(),
                    stat.S_IMODE(value.st_mode),
                    len(content),
                    before[relative],
                )
            )
        after, after_folders = inventory()
        if before != after or folders != after_folders:
            raise SnapshotChangedError("snapshot_changed:list")
        for item in captured:
            checkpoint()
            content = read_regular(root / item.path, max_file_bytes)
            if (
                hashlib.sha256(content).hexdigest() != item.sha256
                or file_identity((root / item.path).lstat()) != item.identity
            ):
                raise SnapshotChangedError("snapshot_changed:" + item.path)
        final, final_folders = inventory()
        if before != final or folders != final_folders:
            raise SnapshotChangedError("snapshot_changed:list")
        checkpoint()
        files = tuple(captured)
        return SourceSnapshot(files, manifest_digest(files))
    except SnapshotError:
        raise
    except (OSError, ValueError) as error:
        raise SnapshotChangedError("snapshot_changed:" + str(error)) from error

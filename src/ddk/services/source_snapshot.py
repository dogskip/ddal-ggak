"""Bounded source captures with stable file lists and verified exact bytes."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Callable, Iterable
from contextlib import ExitStack
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


def source_matches(
    path: Path, snapshot: SourceSnapshot, *, max_file_bytes: int, max_total_bytes: int
) -> bool:
    """Exact source content, modes and list after execution."""
    try:
        observed = capture_source(
            path, max_file_bytes=max_file_bytes, max_total_bytes=max_total_bytes
        )
        return observed.tree_sha256 == snapshot.tree_sha256
    except (OSError, ValueError):
        return False


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
        with ExitStack() as opened:
            checkpoint()
            before, folders = inventory()
            pins: dict[str, int] = {}
            for relative, identity in before.items():
                checkpoint()
                with parent_descriptor(root / relative) as (parent_fd, name):
                    descriptor = os.open(
                        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
                    )
                    opened.callback(os.close, descriptor)
                pins[relative] = descriptor
                if file_identity(os.fstat(descriptor)) != identity:
                    raise SnapshotChangedError("snapshot_changed:" + relative)
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
            for relative, descriptor in pins.items():
                if file_identity(os.fstat(descriptor)) != before[relative]:
                    raise SnapshotChangedError("snapshot_changed:" + relative)
            checkpoint()
            files = tuple(captured)
            return SourceSnapshot(files, manifest_digest(files))
    except SnapshotError:
        raise
    except (OSError, ValueError) as error:
        raise SnapshotChangedError("snapshot_changed:" + str(error)) from error


def _git(repository: Path, args: list[str], limit: int = 2 * 1024**2) -> bytes:
    import subprocess
    import tempfile

    with tempfile.TemporaryFile() as output:
        result = subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=/dev/null",
                "--no-pager",
                "--no-replace-objects",
                "-c",
                "core.fsmonitor=false",
                "-C",
                str(repository),
                *args,
            ],
            stdout=output,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        if result.returncode:
            raise SnapshotError("git_snapshot_unavailable")
        output.seek(0)
        data = output.read(limit + 1)
        if len(data) > limit:
            raise SnapshotError("git_output_limit")
        return data


def resolve_git_ref(repository: Path, ref: str) -> str:
    import re

    if not ref or ref.startswith("-") or len(ref) > 128 or "\x00" in ref:
        raise SnapshotError("invalid_git_ref")
    value = (
        _git(repository, ["rev-parse", "--verify", "--end-of-options", ref + "^{commit}"])
        .decode()
        .strip()
    )
    if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", value) is None:
        raise SnapshotError("invalid_git_ref")
    return value


def capture_git_source(
    repository: Path,
    ref: str,
    *,
    max_file_bytes: int = 2 * 1024**2,
    max_total_bytes: int = 200 * 1024**2,
) -> SourceSnapshot:
    commit = resolve_git_ref(repository, ref)
    listing = _git(repository, ["ls-tree", "-rz", "--full-tree", "--long", commit])
    files: list[SnapshotFile] = []
    total = 0
    for entry in listing.split(b"\x00"):
        if not entry:
            continue
        metadata, raw = entry.split(b"\t", 1)
        mode, kind, oid, size = metadata.split()
        name = raw.decode("utf-8", errors="strict")
        try:
            normalize_source_path(name)
        except ValueError:
            continue
        if mode not in {b"100644", b"100755"} or kind != b"blob":
            raise SnapshotError("git_regular_file_required")
        if int(size) > max_file_bytes:
            raise SnapshotError("snapshot_file_size_limit")
        total += int(size)
        if total > max_total_bytes or len(files) >= 10000:
            raise SnapshotError("snapshot_total_size_limit")
        content = _git(repository, ["cat-file", "blob", oid.decode()], max_file_bytes)
        if len(content) != int(size):
            raise SnapshotChangedError("git_blob_changed")
        files.append(
            SnapshotFile(
                name,
                content,
                hashlib.sha256(content).hexdigest(),
                0o755 if mode == b"100755" else 0o644,
                len(content),
            )
        )
    result = tuple(files)
    return SourceSnapshot(result, manifest_digest(result))


def capture_git_worktree(
    repository: Path, *, max_file_bytes: int = 2 * 1024**2, max_total_bytes: int = 200 * 1024**2
) -> SourceSnapshot:
    def names() -> list[str]:
        values = set(
            _git(repository, ["ls-files", "-z", "--cached", "--others", "--exclude-standard"])
            .decode("utf-8", errors="strict")
            .split("\x00")
        ) - {""}
        if len(values) > 10000:
            raise SnapshotError("snapshot_file_count_limit")
        permitted: list[str] = []
        for value in sorted(values):
            try:
                normalize_source_path(value)
            except ValueError:
                continue
            permitted.append(value)
        ensure_distinct_paths(permitted)
        return permitted

    first = names()
    files: list[SnapshotFile] = []
    missing: list[str] = []
    total = 0
    for name in first:
        path = repository / name
        try:
            value = path.lstat()
        except FileNotFoundError:
            missing.append(name)
            continue
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise SnapshotError("snapshot_regular_file_required")
        content = read_regular(path, max_file_bytes)
        if file_identity(value) != file_identity(path.lstat()):
            raise SnapshotChangedError("snapshot_changed")
        total += len(content)
        if total > max_total_bytes:
            raise SnapshotError("snapshot_total_size_limit")
        files.append(
            SnapshotFile(
                name,
                content,
                hashlib.sha256(content).hexdigest(),
                stat.S_IMODE(value.st_mode),
                len(content),
                file_identity(value),
            )
        )
    if first != names():
        raise SnapshotChangedError("snapshot_changed:list")
    if any((repository / name).exists() or (repository / name).is_symlink() for name in missing):
        raise SnapshotChangedError("snapshot_changed:reappeared")
    for item in files:
        path = repository / item.path
        if (
            file_identity(path.lstat()) != item.identity
            or read_regular(path, max_file_bytes) != item.content
        ):
            raise SnapshotChangedError("snapshot_changed:" + item.path)
    captured = tuple(files)
    return SourceSnapshot(captured, manifest_digest(captured))


def materialize_snapshot(snapshot: SourceSnapshot, directory: Path) -> None:
    from ddk.services.durable_files import atomic_write, ensure_directory

    ensure_directory(directory)
    for item in snapshot.files:
        if not safe_path(item.path):
            raise SnapshotError("unsafe_snapshot_path")
        path = directory / item.path
        ensure_directory(path.parent)
        atomic_write(path, item.content, mode=item.mode, exclusive=True)

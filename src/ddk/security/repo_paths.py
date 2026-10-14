"""Repository-relative path policy shared by every filesystem boundary."""

from __future__ import annotations

import re
import stat
import unicodedata
from pathlib import Path

from ddk.security.secret_paths import is_secret_path

_NON_SOURCE_DIR_PARTS = frozenset({"node_modules", ".venv", "__pycache__"})
_BUILD_OUTPUT_DIRS = frozenset({"dist", ".next", ".turbo", "coverage"})

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
_CHANGE_CONFIG = re.compile(
    r"(^|/)(package(-lock)?\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|\.gitignore"
    r"|tsconfig[^/]*\.json|(vite|next|vitest|eslint)\.config\.[^/]+|\.eslintrc[^/]*)$",
    re.IGNORECASE,
)


class UnsafeRepositoryPathError(ValueError):
    """Raised when an untrusted path violates its repository boundary."""


def normalize_repo_relative_path(raw_path: str) -> str:
    """Validate exact POSIX spelling; owned storage paths remain available."""
    invalid = (
        not raw_path
        or raw_path != raw_path.strip()
        or raw_path.startswith("/")
        or _WINDOWS_DRIVE.match(raw_path) is not None
        or "\\" in raw_path
        or any(ord(char) < 32 or ord(char) == 127 for char in raw_path)
    )
    parts = raw_path.split("/")
    if invalid or any(part in {"", ".", ".."} for part in parts):
        raise UnsafeRepositoryPathError(f"unsafe repository-relative path: {raw_path!r}")
    return raw_path


def normalize_source_path(raw_path: str) -> str:
    """Validate a repository input, excluding private and tool-owned paths."""
    path = normalize_repo_relative_path(raw_path)
    if (
        is_secret_path(path)
        or path.split("/")[0].lower() in _BUILD_OUTPUT_DIRS
        or any(part.lower() in _NON_SOURCE_DIR_PARTS for part in path.split("/"))
    ):
        raise UnsafeRepositoryPathError(f"protected repository path: {raw_path!r}")
    return path


def normalize_change_path(raw_path: str) -> str:
    """Validate a model change without granting access to execution configuration."""
    path = normalize_source_path(raw_path)
    if _CHANGE_CONFIG.search(path) is not None:
        raise UnsafeRepositoryPathError(f"protected repository configuration: {raw_path!r}")
    return path


def ensure_distinct_paths(paths: list[str]) -> None:
    """Reject path collisions on case-insensitive or Unicode-normalizing filesystems."""
    identities = [unicodedata.normalize("NFC", path).casefold() for path in paths]
    if len(identities) != len(set(identities)):
        raise UnsafeRepositoryPathError("repository paths collide after name normalization")


def resolve_within_repository(root: Path, raw_path: str) -> Path:
    """Resolve an owned path, rejecting symlinks, special files and shared inodes."""
    normalized = normalize_repo_relative_path(raw_path)
    if root.is_symlink():
        raise UnsafeRepositoryPathError(f"repository root is a symlink: {root}")
    resolved_root = root.resolve()
    parts = normalized.split("/")
    current = resolved_root
    for index, part in enumerate(parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise UnsafeRepositoryPathError(
                f"cannot inspect repository path: {raw_path!r}"
            ) from exc
        parent = index < len(parts) - 1
        if (
            stat.S_ISLNK(info.st_mode)
            or (parent and not stat.S_ISDIR(info.st_mode))
            or (not parent and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))
        ):
            raise UnsafeRepositoryPathError(f"unsafe repository file type: {raw_path!r}")
    if not current.is_relative_to(resolved_root):
        raise UnsafeRepositoryPathError(f"repository path escapes its root: {raw_path!r}")
    return current


def resolve_source_path(root: Path, raw_path: str) -> Path:
    """Resolve a permitted repository source file or prospective source path."""
    return resolve_within_repository(root, normalize_source_path(raw_path))


def resolve_change_path(root: Path, raw_path: str) -> Path:
    """Resolve a permitted model change target immediately before access."""
    return resolve_within_repository(root, normalize_change_path(raw_path))


def read_source(root: Path, raw_path: str, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    """Read an approved ordinary repository file through the shared file boundary."""
    from ddk.security.file_access import read_regular

    return read_regular(resolve_source_path(root, raw_path), max_bytes)

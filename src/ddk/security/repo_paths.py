"""Repository-relative path policy shared by every filesystem boundary."""

from __future__ import annotations

import re
from pathlib import Path

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


class UnsafeRepositoryPathError(ValueError):
    """Raised when an untrusted path can address data outside its repository root."""


def normalize_repo_relative_path(raw_path: str) -> str:
    """Return a canonical POSIX-style repository-relative path or reject it."""
    normalized = raw_path.replace("\\", "/")
    invalid = (
        not normalized
        or normalized != normalized.strip()
        or normalized.startswith("/")
        or normalized.startswith("//")
        or _WINDOWS_DRIVE.match(normalized) is not None
        or "\x00" in normalized
    )
    parts = normalized.split("/")
    if invalid or any(part in {"", ".", ".."} for part in parts):
        raise UnsafeRepositoryPathError(f"unsafe repository-relative path: {raw_path!r}")
    return "/".join(parts)


def resolve_within_repository(root: Path, raw_path: str) -> Path:
    """Resolve an untrusted relative path beneath ``root`` without following symlinks."""
    normalized = normalize_repo_relative_path(raw_path)
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*normalized.split("/"))

    current = resolved_root
    for part in normalized.split("/"):
        current = current / part
        if current.is_symlink():
            raise UnsafeRepositoryPathError(
                f"unsafe repository-relative path: {raw_path!r} traverses a symlink"
            )

    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(resolved_root):
        raise UnsafeRepositoryPathError(
            f"unsafe repository-relative path: {raw_path!r} escapes {resolved_root}"
        )
    return resolved

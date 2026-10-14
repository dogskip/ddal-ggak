"""Descriptor-based access to bounded, unshared regular files."""

from __future__ import annotations

import os
import stat
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def parent_descriptor(path: Path) -> Generator[tuple[int, str]]:
    """Open each parent without following a symbolic link."""
    absolute = Path(os.path.abspath(path))
    if not absolute.name:
        raise ValueError("file_name_required")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(absolute.anchor, flags)
    try:
        for part in absolute.parts[1:-1]:
            following = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = following
        yield descriptor, absolute.name
    finally:
        os.close(descriptor)


def file_identity(value: os.stat_result) -> tuple[int, ...]:
    """Return the state that must stay fixed across a bounded read."""
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def read_regular_at(parent_fd: int, name: str, max_bytes: int) -> bytes:
    """Read one child from an already pinned directory."""
    if max_bytes < 0:
        raise ValueError("negative_size_limit")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError("unshared_regular_file_required")
        if before.st_size > max_bytes:
            raise ValueError("file_size_limit")
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            len(payload) > max_bytes
            or len(payload) != before.st_size
            or file_identity(before) != file_identity(after)
            or file_identity(after) != file_identity(current)
        ):
            raise ValueError("file_changed_during_read")
        return payload
    finally:
        os.close(descriptor)


def read_regular(path: Path, max_bytes: int) -> bytes:
    """Reject aliases, oversized data and replacement during the read."""
    with parent_descriptor(path) as (parent_fd, name):
        return read_regular_at(parent_fd, name, max_bytes)

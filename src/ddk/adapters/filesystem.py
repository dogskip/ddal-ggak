"""Filesystem adapter Protocol and real implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class FilesystemPort(Protocol):
    """Protocol for filesystem operations."""

    def read_text(self, path: Path) -> str: ...

    def write_text(self, path: Path, content: str) -> None: ...

    def list_dir(self, path: Path) -> list[Path]: ...

    def exists(self, path: Path) -> bool: ...

    def mkdir(self, path: Path, parents: bool = True) -> None: ...

    def read_bytes(self, path: Path) -> bytes: ...

    def write_bytes(self, path: Path, content: bytes) -> None: ...


class FilesystemAdapter:
    """Real filesystem implementation."""

    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write_text(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def list_dir(self, path: Path) -> list[Path]:
        return sorted(path.iterdir())

    def exists(self, path: Path) -> bool:
        return path.exists()

    def mkdir(self, path: Path, parents: bool = True) -> None:
        path.mkdir(parents=parents, exist_ok=True)

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def write_bytes(self, path: Path, content: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

"""InMemoryFilesystem — dict-backed filesystem fake. No disk I/O."""

from __future__ import annotations

from pathlib import Path


class InMemoryFilesystem:
    """Dict-backed filesystem. No disk I/O."""

    def __init__(self) -> None:
        self._files: dict[str, str] = {}
        self._binary_files: dict[str, bytes] = {}
        self._dirs: set[str] = set()

    def read_text(self, path: Path) -> str:
        key = str(path)
        if key not in self._files:
            raise FileNotFoundError(f"No such file: {path}")
        return self._files[key]

    def write_text(self, path: Path, content: str) -> None:
        self._files[str(path)] = content
        self._dirs.add(str(path.parent))

    def list_dir(self, path: Path) -> list[Path]:
        prefix = str(path)
        result: list[Path] = []
        seen: set[str] = set()
        for key in self._files:
            if key.startswith(prefix + "/"):
                relative = key[len(prefix) + 1 :]
                top_level = relative.split("/")[0]
                if top_level not in seen:
                    seen.add(top_level)
                    result.append(path / top_level)
        return sorted(result)

    def exists(self, path: Path) -> bool:
        key = str(path)
        return key in self._files or key in self._dirs or key in self._binary_files

    def mkdir(self, path: Path, parents: bool = True) -> None:
        self._dirs.add(str(path))
        if parents:
            for parent in path.parents:
                self._dirs.add(str(parent))

    def read_bytes(self, path: Path) -> bytes:
        key = str(path)
        if key not in self._binary_files:
            raise FileNotFoundError(f"No such file: {path}")
        return self._binary_files[key]

    def write_bytes(self, path: Path, content: bytes) -> None:
        self._binary_files[str(path)] = content
        self._dirs.add(str(path.parent))

"""Real, decodable image files for tests that go through Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def write_png(
    path: Path, size: tuple[int, int] = (64, 48), color: tuple[int, int, int] = (250, 250, 250)
) -> Path:
    """Write a flat-colour PNG and return its path."""
    Image.new("RGB", size, color).save(path, format="PNG")
    return path

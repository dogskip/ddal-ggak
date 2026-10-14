"""Screenshot diff adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class SSIMResult:
    """Result of SSIM comparison between two screenshots."""

    score: float  # 0.0 to 1.0
    mismatch_regions: list[dict[str, int]]  # [{x, y, width, height, dissimilarity 0-100}]
    diff_image_path: Path | None = None
    changed_pixel_ratio: float = 0.0  # share of pixels whose brightness differs visibly
    mismatch_area_ratio: float = 0.0  # share of 8x8 blocks that disagree strongly (SSIM < 0.5)


@runtime_checkable
class ScreenshotDiffAdapter(Protocol):
    """Protocol for screenshot comparison via SSIM."""

    def compute_ssim(self, reference: Path, generated: Path) -> SSIMResult: ...

    def generate_diff_image(self, reference: Path, generated: Path, output: Path) -> Path: ...

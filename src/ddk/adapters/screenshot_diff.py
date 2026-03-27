"""Screenshot diff adapter Protocol and supporting types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass
class SSIMResult:
    """Result of SSIM comparison between two screenshots."""

    score: float  # 0.0 to 1.0
    mismatch_regions: list[dict[str, int]]  # [{x, y, width, height}]
    diff_image_path: Path | None = None


@runtime_checkable
class ScreenshotDiffAdapter(Protocol):
    """Protocol for screenshot comparison via SSIM."""

    def compute_ssim(
        self, reference: Path, generated: Path
    ) -> SSIMResult: ...

    def generate_diff_image(
        self, reference: Path, generated: Path, output: Path
    ) -> Path: ...

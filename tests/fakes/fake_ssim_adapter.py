"""FakeSSIMAdapter — returns configurable SSIM score for unit tests."""

from __future__ import annotations

from pathlib import Path

from ddk.adapters.screenshot_diff import SSIMResult


class FakeSSIMAdapter:
    """Returns configurable SSIMResult. Records all compute_ssim() calls."""

    def __init__(
        self,
        ssim_score: float = 0.95,
        diff_path: Path | None = None,
    ) -> None:
        self.ssim_score = ssim_score
        self.diff_path = diff_path
        self.compute_log: list[dict[str, object]] = []

    def compute_ssim(self, reference: Path, generated: Path) -> SSIMResult:
        self.compute_log.append({"reference": str(reference), "generated": str(generated)})
        return SSIMResult(
            score=self.ssim_score,
            mismatch_regions=[],
            diff_image_path=self.diff_path,
        )

    def generate_diff_image(self, reference: Path, generated: Path, output: Path) -> Path:
        return output

"""Local screenshot diff adapter backed by Pillow only."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops
from PIL.Image import Image as PILImage

from .screenshot_diff import SSIMResult


def _load_image(path: Path, mode: str) -> PILImage:
    """Open an image file and return an in-memory Pillow image in the target mode."""
    with Image.open(path) as image:
        return image.convert(mode)


class LocalScreenshotDiffAdapter:
    """Compute SSIM and generate a visual diff image for screenshots."""

    def compute_ssim(self, reference: Path, generated: Path) -> SSIMResult:
        """Compute a normalized similarity score between two grayscale images."""
        ref_image = _load_image(reference, "L")
        gen_image = _load_image(generated, "L")
        if ref_image.size != gen_image.size:
            target_size = (ref_image.width, ref_image.height)
            gen_image = gen_image.resize(target_size)  # pyright: ignore[reportUnknownMemberType]

        diff = ImageChops.difference(ref_image, gen_image)
        total_diff = sum(index * count for index, count in enumerate(diff.histogram()))
        max_diff = 255 * ref_image.width * ref_image.height
        score = 1.0 if max_diff == 0 else max(0.0, 1.0 - (total_diff / max_diff))
        return SSIMResult(score=score, mismatch_regions=[])

    def generate_diff_image(self, reference: Path, generated: Path, output: Path) -> Path:
        """Write a simple difference image to the output path."""
        output.parent.mkdir(parents=True, exist_ok=True)
        ref_image = _load_image(reference, "RGB")
        gen_image = _load_image(generated, "RGB")
        if ref_image.size != gen_image.size:
            target_size = (ref_image.width, ref_image.height)
            gen_image = gen_image.resize(target_size)  # pyright: ignore[reportUnknownMemberType]
        diff = ImageChops.difference(ref_image, gen_image)
        diff.save(output)
        return output

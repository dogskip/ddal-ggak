"""Local screenshot comparison on Pillow only: block SSIM, mismatch regions, diff image."""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageMath
from PIL.Image import Image as PILImage

from .screenshot_diff import SSIMResult

_BLOCK = 8
_C1 = (0.01 * 255) ** 2
_C2 = (0.03 * 255) ** 2
_MISMATCH_BELOW = 0.5
_CHANGED_LEVELS = 13
_MAX_REGIONS = 20
_OVERLAY_STRENGTH = 200


@dataclass
class _Comparison:
    """Per-block similarity of two same-sized images."""

    values: list[float]
    cols: int
    rows: int
    width: int
    height: int
    identical: bool
    changed_ratio: float

    @property
    def mismatch_ratio(self) -> float:
        return sum(value < _MISMATCH_BELOW for value in self.values) / len(self.values)

    @property
    def score(self) -> float:
        if self.identical:
            return 1.0
        return max(0.0, min(1.0, sum(self.values) / len(self.values)))


def flatten_to_rgb(image: PILImage) -> PILImage:
    """RGB copy of the image; transparent areas are composited on white."""
    if image.mode in {"RGBA", "LA", "PA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        canvas = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        canvas.alpha_composite(rgba)
        return canvas.convert("RGB")
    return image.convert("RGB")


def _load_rgb(path: Path) -> PILImage:
    with Image.open(path) as image:
        return flatten_to_rgb(image)


def _load_pair(reference: Path, generated: Path) -> tuple[PILImage, PILImage]:
    """Both images as RGB at the reference size.

    The generated image is scaled evenly to the reference width, then cropped or padded at the
    bottom to the reference height, so content stays where the page put it.
    """
    ref = _load_rgb(reference)
    gen = _load_rgb(generated)
    if gen.width != ref.width:
        height = max(1, round(gen.height * ref.width / gen.width))
        gen = gen.resize((ref.width, height), Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
    if gen.height > ref.height:
        gen = gen.crop((0, 0, ref.width, ref.height))
    elif gen.height < ref.height:
        background = gen.getpixel((0, gen.height - 1))  # pyright: ignore[reportUnknownMemberType]
        padded = Image.new("RGB", ref.size, background)  # pyright: ignore[reportArgumentType]
        padded.paste(gen, (0, 0))
        gen = padded
    return ref, gen


def _block_means(image: PILImage, size: tuple[int, int]) -> PILImage:
    return image.resize(size, Image.Resampling.BOX)  # pyright: ignore[reportUnknownMemberType]


def _block_similarity(ref: PILImage, gen: PILImage) -> _Comparison:
    ref_gray, gen_gray = ref.convert("L"), gen.convert("L")
    width, height = ref_gray.size
    identical = ImageChops.difference(ref_gray, gen_gray).getbbox() is None
    cols = max(1, round(width / _BLOCK))
    rows = max(1, round(height / _BLOCK))
    if identical:
        return _Comparison([1.0] * (cols * rows), cols, rows, width, height, True, 0.0)

    x, y = ref_gray.convert("F"), gen_gray.convert("F")
    grid = (cols, rows)
    squares = {
        "xx": ImageMath.lambda_eval(lambda a: a["x"] * a["x"], x=x),
        "yy": ImageMath.lambda_eval(lambda a: a["y"] * a["y"], y=y),
        "xy": ImageMath.lambda_eval(lambda a: a["x"] * a["y"], x=x, y=y),
    }
    similarity = ImageMath.lambda_eval(
        lambda a: (
            (a["mx"] * a["my"] * 2 + _C1)
            * ((a["mxy"] - a["mx"] * a["my"]) * 2 + _C2)
            / (
                (a["mx"] * a["mx"] + a["my"] * a["my"] + _C1)
                * ((a["mxx"] - a["mx"] * a["mx"]) + (a["myy"] - a["my"] * a["my"]) + _C2)
            )
        ),
        mx=_block_means(x, grid),
        my=_block_means(y, grid),
        mxx=_block_means(squares["xx"], grid),
        myy=_block_means(squares["yy"], grid),
        mxy=_block_means(squares["xy"], grid),
    )
    values = array("f")
    values.frombytes(similarity.convert("F").tobytes())
    return _Comparison(
        [max(0.0, min(1.0, float(v))) for v in values],
        cols,
        rows,
        width,
        height,
        False,
        _changed_ratio(ref_gray, gen_gray),
    )


def _changed_ratio(ref_gray: PILImage, gen_gray: PILImage) -> float:
    histogram = ImageChops.difference(ref_gray, gen_gray).histogram()
    return sum(histogram[_CHANGED_LEVELS + 1 :]) / (ref_gray.width * ref_gray.height)


def _mismatch_regions(comparison: _Comparison) -> list[dict[str, int]]:
    """Bounding boxes (reference pixels) of connected low-similarity blocks, largest first."""
    cols, rows, values = comparison.cols, comparison.rows, comparison.values
    bad = [value < _MISMATCH_BELOW for value in values]
    seen = [False] * len(values)
    found: list[dict[str, int]] = []

    for start, is_bad in enumerate(bad):
        if not is_bad or seen[start]:
            continue
        seen[start] = True
        stack: list[int] = [start]
        cells: list[int] = []
        while stack:
            index = stack.pop()
            cells.append(index)
            row, col = divmod(index, cols)
            for next_row in range(max(0, row - 1), min(rows, row + 2)):
                for next_col in range(max(0, col - 1), min(cols, col + 2)):
                    neighbour = next_row * cols + next_col
                    if bad[neighbour] and not seen[neighbour]:
                        seen[neighbour] = True
                        stack.append(neighbour)
        found.append(_region_of(cells, comparison))

    found.sort(key=lambda r: (r["width"] * r["height"], r["dissimilarity"]), reverse=True)
    return found[:_MAX_REGIONS]


def _region_of(cells: list[int], comparison: _Comparison) -> dict[str, int]:
    cols = comparison.cols
    first_col = min(index % cols for index in cells)
    last_col = max(index % cols for index in cells)
    first_row = min(index // cols for index in cells)
    last_row = max(index // cols for index in cells)
    left = first_col * comparison.width // cols
    top = first_row * comparison.height // comparison.rows
    right = -(-(last_col + 1) * comparison.width // cols)
    bottom = -(-(last_row + 1) * comparison.height // comparison.rows)
    dissimilarity = sum(1.0 - comparison.values[index] for index in cells) / len(cells)
    return {
        "x": left,
        "y": top,
        "width": min(right, comparison.width) - left,
        "height": min(bottom, comparison.height) - top,
        "dissimilarity": round(dissimilarity * 100),
    }


class LocalScreenshotDiffAdapter:
    """Block-wise SSIM, mismatch regions and a diff image for screenshots."""

    def compute_ssim(self, reference: Path, generated: Path) -> SSIMResult:
        """Mean block SSIM (8x8 blocks, grayscale) of the generated image against the reference.

        The generated image is first fitted to the reference: scaled evenly to its width, then
        cropped or padded at the bottom to its height. Regions are the bounding boxes of
        connected blocks whose SSIM is below 0.5.
        """
        ref, gen = _load_pair(reference, generated)
        comparison = _block_similarity(ref, gen)
        return SSIMResult(
            score=comparison.score,
            mismatch_regions=[] if comparison.identical else _mismatch_regions(comparison),
            changed_pixel_ratio=comparison.changed_ratio,
            mismatch_area_ratio=0.0 if comparison.identical else comparison.mismatch_ratio,
        )

    def generate_diff_image(self, reference: Path, generated: Path, output: Path) -> Path:
        """Write the generated image with mismatching blocks tinted red."""
        output.parent.mkdir(parents=True, exist_ok=True)
        ref, gen = _load_pair(reference, generated)
        comparison = _block_similarity(ref, gen)
        if comparison.identical:
            gen.save(output)
            return output

        dissimilarity = Image.new("F", (comparison.cols, comparison.rows))
        dissimilarity.frombytes(
            array("f", [0.0 if v >= 0.8 else 1.0 - v for v in comparison.values]).tobytes()
        )
        strength = ImageMath.lambda_eval(lambda a: a["d"] * _OVERLAY_STRENGTH, d=dissimilarity)
        mask = strength.convert("L").resize(ref.size, Image.Resampling.NEAREST)  # pyright: ignore[reportUnknownMemberType]
        tint = Image.new("RGB", ref.size, (255, 0, 0))
        Image.composite(tint, gen, mask).save(output)
        return output

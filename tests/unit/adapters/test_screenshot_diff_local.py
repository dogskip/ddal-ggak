"""Tests for LocalScreenshotDiffAdapter — Pillow-based SSIM."""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter


class TestLocalScreenshotDiffAdapter:
    def _create_solid_image(self, path: Path, color: tuple) -> None:
        from PIL import Image

        img = Image.new("RGB", (100, 100), color)
        img.save(str(path))

    def test_identical_images_high_ssim(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.png"
        gen = tmp_path / "gen.png"
        self._create_solid_image(ref, (255, 0, 0))
        self._create_solid_image(gen, (255, 0, 0))

        adapter = LocalScreenshotDiffAdapter()
        result = adapter.compute_ssim(ref, gen)

        assert result.score > 0.99

    def test_different_images_lower_ssim(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.png"
        gen = tmp_path / "gen.png"
        self._create_solid_image(ref, (255, 0, 0))
        self._create_solid_image(gen, (0, 0, 255))

        adapter = LocalScreenshotDiffAdapter()
        result = adapter.compute_ssim(ref, gen)

        assert result.score < 1.0

    def test_generate_diff_image(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.png"
        gen = tmp_path / "gen.png"
        diff_out = tmp_path / "diff.png"
        self._create_solid_image(ref, (255, 0, 0))
        self._create_solid_image(gen, (0, 255, 0))

        adapter = LocalScreenshotDiffAdapter()
        adapter.generate_diff_image(ref, gen, diff_out)

        assert diff_out.exists()

    def test_score_range(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.png"
        gen = tmp_path / "gen.png"
        self._create_solid_image(ref, (128, 128, 128))
        self._create_solid_image(gen, (130, 128, 126))

        adapter = LocalScreenshotDiffAdapter()
        result = adapter.compute_ssim(ref, gen)

        assert 0.0 <= result.score <= 1.0


def _textured(size: tuple[int, int] = (320, 200)) -> Image.Image:
    """A page-like image: diagonal gradient plus a few filled boxes."""
    image = Image.new("L", size)
    pixels = [(x * 3 + y * 5) % 200 + 20 for y in range(size[1]) for x in range(size[0])]
    image.putdata(pixels)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 120, 60), fill=250)
    draw.rectangle((180, 100, 300, 180), fill=10)
    return image


class TestBlockSimilarity:
    def test_untouched_copy_scores_exactly_one(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        _textured().save(ref)
        _textured().save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score == 1.0
        assert result.mismatch_regions == []
        assert result.changed_pixel_ratio == 0.0

    def test_faint_noise_is_tolerated(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        base = _textured()
        rng = random.Random(7)
        noisy = Image.new("L", base.size)
        noisy.putdata([min(255, max(0, v + rng.randint(-2, 2))) for v in base.tobytes()])
        base.save(ref)
        noisy.save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score >= 0.95
        assert result.mismatch_regions == []

    def test_local_change_is_located(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        base = _textured()
        changed = base.copy()
        ImageDraw.Draw(changed).rectangle((200, 20, 263, 67), fill=0)
        base.save(ref)
        changed.save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert 0.80 < result.score < 1.0
        assert len(result.mismatch_regions) == 1
        region = result.mismatch_regions[0]
        assert region["x"] <= 200 and region["x"] + region["width"] >= 264
        assert region["y"] <= 20 and region["y"] + region["height"] >= 68
        assert region["width"] <= 64 + 16 and region["height"] <= 48 + 16
        assert 0 < result.changed_pixel_ratio < 0.10

    def test_sparse_page_with_moved_content_is_not_hidden_by_blank_space(
        self, tmp_path: Path
    ) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        blank_ref = Image.new("L", (640, 400), 255)
        blank_gen = Image.new("L", (640, 400), 255)
        ImageDraw.Draw(blank_ref).rectangle((40, 40, 240, 160), fill=0)
        ImageDraw.Draw(blank_gen).rectangle((380, 220, 580, 340), fill=0)
        blank_ref.save(ref)
        blank_gen.save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score < 0.92
        assert len(result.mismatch_regions) == 2

    def test_regions_are_capped_and_largest_first(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        flat = Image.new("L", (800, 800), 255)
        speckled = flat.copy()
        draw = ImageDraw.Draw(speckled)
        for index in range(40):
            x, y = (index % 8) * 100 + 10, (index // 8) * 100 + 10
            size = 16 + index
            draw.rectangle((x, y, x + size, y + size), fill=0)
        flat.save(ref)
        speckled.save(gen)

        regions = LocalScreenshotDiffAdapter().compute_ssim(ref, gen).mismatch_regions

        assert len(regions) == 20
        areas = [r["width"] * r["height"] for r in regions]
        assert areas == sorted(areas, reverse=True)

    def test_image_smaller_than_one_block_still_scores(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        Image.new("L", (5, 3), 0).save(ref)
        Image.new("L", (5, 3), 255).save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score < 0.1

    def test_alpha_channel_is_flattened_on_white(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(ref)
        Image.new("RGB", (64, 64), (255, 255, 255)).save(gen)

        assert LocalScreenshotDiffAdapter().compute_ssim(ref, gen).score == 1.0

    def test_diff_image_marks_the_mismatch_and_matches_reference_size(self, tmp_path: Path) -> None:
        ref, gen, out = tmp_path / "ref.png", tmp_path / "gen.png", tmp_path / "out" / "diff.png"
        base = _textured()
        changed = base.copy()
        ImageDraw.Draw(changed).rectangle((200, 20, 263, 67), fill=0)
        base.save(ref)
        changed.save(gen)

        LocalScreenshotDiffAdapter().generate_diff_image(ref, gen, out)

        with Image.open(out) as diff:
            assert diff.size == base.size
            inside = diff.convert("RGB").getpixel((230, 40))
            outside = diff.convert("RGB").getpixel((30, 150))
        assert isinstance(inside, tuple) and isinstance(outside, tuple)
        assert inside[0] > inside[2] + 60  # reddish where the pages disagree
        assert abs(outside[0] - outside[2]) < 30  # untouched elsewhere


class TestMismatchAreaRatio:
    def test_ratio_is_the_share_of_blocks_that_disagree_strongly(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        Image.new("L", (320, 200), 255).save(ref)
        page = Image.new("L", (320, 200), 255)
        ImageDraw.Draw(page).rectangle((64, 48, 127, 95), fill=0)  # 8 x 6 aligned blocks
        page.save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.mismatch_area_ratio == pytest.approx(48 / 1000)
        assert result.score > 0.95  # blank space hides it from the mean; the ratio does not

    def test_identical_images_have_no_mismatch(self, tmp_path: Path) -> None:
        ref = tmp_path / "ref.png"
        _textured().save(ref)

        assert LocalScreenshotDiffAdapter().compute_ssim(ref, ref).mismatch_area_ratio == 0.0


class TestDifferentSizes:
    """The page is compared where it is, not squeezed to fit: only its height may differ."""

    def test_page_taller_than_the_design_is_cropped_not_squashed(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        design = _textured((320, 200))
        taller = Image.new("L", (320, 216), 90)  # e.g. 100vh plus the default body margin
        taller.paste(design, (0, 0))
        design.save(ref)
        taller.save(gen)
        adapter = LocalScreenshotDiffAdapter()

        result = adapter.compute_ssim(ref, gen)
        diff = adapter.generate_diff_image(ref, gen, tmp_path / "diff.png")

        assert result.score == 1.0
        assert result.mismatch_regions == []
        with Image.open(diff) as image:
            assert image.size == (320, 200)

    def test_page_shorter_than_the_design_is_padded_with_its_own_background(
        self, tmp_path: Path
    ) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        design = Image.new("RGB", (320, 200), (245, 247, 250))
        ImageDraw.Draw(design).rectangle((20, 20, 120, 60), fill=(15, 23, 42))
        design.save(ref)
        design.crop((0, 0, 320, 184)).save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score == 1.0
        assert result.mismatch_regions == []

    def test_page_that_stops_far_too_early_is_reported(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        design = _textured((320, 400))
        design.save(ref)
        design.crop((0, 0, 320, 100)).save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score < 0.92
        assert result.mismatch_regions

    def test_capture_at_half_the_width_is_scaled_up_evenly(self, tmp_path: Path) -> None:
        ref, gen = tmp_path / "ref.png", tmp_path / "gen.png"
        design = Image.new("RGB", (640, 400), (255, 255, 255))
        ImageDraw.Draw(design).rectangle((80, 80, 320, 240), fill=(30, 64, 175))
        design.save(ref)
        design.resize((320, 200), Image.Resampling.LANCZOS).save(gen)

        result = LocalScreenshotDiffAdapter().compute_ssim(ref, gen)

        assert result.score >= 0.95

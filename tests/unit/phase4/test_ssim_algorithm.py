"""Unit tests verifying the Pillow-based SSIM algorithm in LocalScreenshotDiffAdapter.

The adapter uses a histogram-based pixel-difference method (not scikit-image SSIM).
These tests validate boundary properties and confirm the 0.92 threshold is reasonable.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PIL import Image

from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _solid_image(width: int, height: int, value: int, *, tmp_path: Path) -> Path:
    """Write a solid-grey PNG and return the path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (width, height), value)
    p = tmp_path / f"solid_{value}_{width}x{height}.png"
    img.save(p)
    return p


def _noisy_image(width: int, height: int, *, seed: int, tmp_path: Path) -> Path:
    """Write a uniformly random (noise) PNG and return the path."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    pixels = [rng.randint(0, 255) for _ in range(width * height)]
    img = Image.new("L", (width, height))
    img.putdata(pixels)  # type: ignore[arg-type]
    p = tmp_path / f"noise_{seed}_{width}x{height}.png"
    img.save(p)
    return p


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestSSIMAlgorithm:
    """Validate the LocalScreenshotDiffAdapter.compute_ssim pixel-diff algorithm."""

    def setup_method(self) -> None:
        self.adapter = LocalScreenshotDiffAdapter()

    # --- Identical images ---------------------------------------------------

    def test_identical_images_score_near_one(self, tmp_path: Path) -> None:
        ref = _solid_image(64, 64, 128, tmp_path=tmp_path / "ref")
        gen = _solid_image(64, 64, 128, tmp_path=tmp_path / "gen")
        result = self.adapter.compute_ssim(ref, gen)
        assert result.score >= 0.99, f"Identical images should score >= 0.99, got {result.score}"

    def test_identical_images_score_exactly_one(self, tmp_path: Path) -> None:
        """Same file path → pixel-perfect → score == 1.0."""
        ref = _solid_image(32, 32, 200, tmp_path=tmp_path / "ref")
        gen = _solid_image(32, 32, 200, tmp_path=tmp_path / "gen")
        result = self.adapter.compute_ssim(ref, gen)
        assert result.score == pytest.approx(1.0, abs=1e-9)

    # --- Total opposites (black vs white) -----------------------------------

    def test_black_vs_white_score_very_low(self, tmp_path: Path) -> None:
        """Completely opposing images should yield a score near 0."""
        black = _solid_image(64, 64, 0, tmp_path=tmp_path / "black")
        white = _solid_image(64, 64, 255, tmp_path=tmp_path / "white")
        result = self.adapter.compute_ssim(black, white)
        assert result.score <= 0.10, f"Black-vs-white should score <= 0.10, got {result.score}"

    # --- Random noise -------------------------------------------------------

    def test_noise_vs_solid_score_well_below_threshold(self, tmp_path: Path) -> None:
        """Pure noise compared to a solid mid-grey should score below 0.92 threshold.

        The histogram-based algorithm gives ~0.75 for uniform random noise vs solid grey
        (expected pixel diff ≈ 85/255 ≈ 33%). The score must stay well below the 0.92
        acceptance threshold so the adapter can correctly flag dissimilar images.
        """
        solid = _solid_image(64, 64, 128, tmp_path=tmp_path / "solid")
        noisy = _noisy_image(64, 64, seed=42, tmp_path=tmp_path / "noise")
        result = self.adapter.compute_ssim(solid, noisy)
        assert result.score <= 0.85, f"Noise-vs-solid should score <= 0.85, got {result.score}"

    # --- Score is bounded ---------------------------------------------------

    def test_score_bounded_between_zero_and_one(self, tmp_path: Path) -> None:
        """score must always be in [0, 1] regardless of image content."""
        a = _noisy_image(32, 32, seed=1, tmp_path=tmp_path / "a")
        b = _noisy_image(32, 32, seed=99, tmp_path=tmp_path / "b")
        result = self.adapter.compute_ssim(a, b)
        assert 0.0 <= result.score <= 1.0

    # --- Size mismatch (auto-resize) ----------------------------------------

    def test_size_mismatch_does_not_raise(self, tmp_path: Path) -> None:
        """Adapter must auto-resize the generated image to match reference dimensions."""
        ref = _solid_image(64, 64, 100, tmp_path=tmp_path / "ref")
        gen = _solid_image(32, 32, 100, tmp_path=tmp_path / "gen")
        result = self.adapter.compute_ssim(ref, gen)
        assert 0.0 <= result.score <= 1.0, "Size-mismatch should not raise and score in [0,1]"

    def test_size_mismatch_identical_content_score_high(self, tmp_path: Path) -> None:
        """After resize, same solid color → score should be close to 1.0."""
        ref = _solid_image(64, 64, 150, tmp_path=tmp_path / "ref2")
        gen = _solid_image(128, 128, 150, tmp_path=tmp_path / "gen2")
        result = self.adapter.compute_ssim(ref, gen)
        assert result.score >= 0.99

    # --- mismatch_regions always empty -------------------------------------

    def test_mismatch_regions_always_empty_list(self, tmp_path: Path) -> None:
        """The Pillow adapter always returns an empty mismatch_regions list."""
        ref = _solid_image(32, 32, 0, tmp_path=tmp_path / "r")
        gen = _solid_image(32, 32, 255, tmp_path=tmp_path / "g")
        result = self.adapter.compute_ssim(ref, gen)
        assert result.mismatch_regions == []

    # --- Threshold sanity check --------------------------------------------

    def test_threshold_0_92_is_below_identical_score(self, tmp_path: Path) -> None:
        """Default threshold 0.92 must be below identical-image score of 1.0."""
        threshold = 0.92
        ref = _solid_image(64, 64, 128, tmp_path=tmp_path / "ref")
        gen = _solid_image(64, 64, 128, tmp_path=tmp_path / "gen")
        result = self.adapter.compute_ssim(ref, gen)
        assert result.score > threshold, (
            f"Identical images ({result.score:.4f}) must exceed threshold {threshold}"
        )

    def test_threshold_0_92_is_above_black_vs_white_score(self, tmp_path: Path) -> None:
        """Default threshold 0.92 must be above the black-vs-white score."""
        threshold = 0.92
        black = _solid_image(64, 64, 0, tmp_path=tmp_path / "black")
        white = _solid_image(64, 64, 255, tmp_path=tmp_path / "white")
        result = self.adapter.compute_ssim(black, white)
        assert result.score < threshold, (
            f"Black-vs-white ({result.score:.4f}) must be below threshold {threshold}"
        )

"""The demo design is a boxes-only wireframe, so any machine draws it identically."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from ddk.adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from ddk.demo.wireframe import (
    Box,
    first_draft_boxes,
    page_source,
    reference_boxes,
    render_boxes,
    render_design,
)


def test_design_image_is_a_1280_by_800_wireframe(tmp_path: Path) -> None:
    path = render_design(tmp_path / "design.png")

    with Image.open(path) as image:
        assert image.size == (1280, 800)
        assert image.convert("RGB").getpixel((5, 5)) == (15, 23, 42)  # header
        assert image.convert("RGB").getpixel((640, 790)) == (241, 245, 249)  # page background
        assert image.convert("RGB").getpixel((300, 280)) == (255, 255, 255)  # card


def test_first_draft_is_close_enough_to_look_plausible_but_fails_the_visual_gate(
    tmp_path: Path,
) -> None:
    reference = render_boxes(reference_boxes(), tmp_path / "ref.png")
    draft = render_boxes(first_draft_boxes(), tmp_path / "draft.png")

    result = LocalScreenshotDiffAdapter().compute_ssim(reference, draft)

    assert result.score < 0.92 or result.mismatch_area_ratio > 0.03
    assert result.score > 0.5
    assert result.mismatch_regions


def test_page_source_draws_every_box_in_order() -> None:
    boxes = [Box(0, 0, 1280, 72, "#0f172a"), Box(32, 24, 160, 24, "#e2e8f0")]

    source = page_source(boxes)

    assert source.index("{ x: 0, y: 0, w: 1280, h: 72, c: '#0f172a' }") < source.index(
        "{ x: 32, y: 24, w: 160, h: 24, c: '#e2e8f0' }"
    )
    assert "export default function App()" in source
    assert "html,body{margin:0}" in source


def test_page_source_for_the_reference_lists_all_its_boxes() -> None:
    boxes = reference_boxes()

    source = page_source(boxes)

    assert source.count("{ x: ") == len(boxes)

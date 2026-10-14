"""A boxes-only dashboard wireframe: the demo's design, its first draft and the page that draws it.

Solid, whole-pixel boxes and no text render the same on every machine, so the repaired page
can match the design exactly wherever the demo runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

PAGE_SIZE = (1280, 800)
_PAGE_COLOR = "#f1f5f9"
_NAVY = "#0f172a"
_SLATE_700 = "#334155"
_SLATE_300 = "#cbd5e1"
_SLATE_200 = "#e2e8f0"
_WHITE = "#ffffff"
_BLUE = "#2563eb"
_GREEN = "#16a34a"
_RED = "#dc2626"
_BARS = (120, 160, 140, 200, 180, 240, 220, 280, 260, 300, 320, 340)


@dataclass(frozen=True)
class Box:
    """A filled rectangle in page pixels; ``color`` is ``#rrggbb``."""

    x: int
    y: int
    w: int
    h: int
    color: str


def reference_boxes() -> list[Box]:
    """The design: dark header, three metric cards, a bar chart."""
    boxes = [Box(0, 0, 1280, 72, _NAVY), Box(32, 24, 160, 24, _SLATE_200)]
    boxes += [Box(x, 28, 80, 16, _SLATE_700) for x in (900, 1000, 1100)]
    for x, accent in zip((32, 448, 864), (_BLUE, _GREEN, _RED), strict=True):
        boxes += _card(x, 104, 384, 200, accent, with_note=True)
    boxes += _chart(32, 336, 1216, 432, _BARS, _BLUE, _GREEN)
    return boxes


def first_draft_boxes() -> list[Box]:
    """What a first attempt could look like: right idea, wrong shades, sizes and spacing."""
    boxes = [Box(0, 0, 1280, 64, _SLATE_700), Box(32, 20, 120, 24, _SLATE_200)]
    for x in (24, 424, 824):
        boxes += _card(x, 96, 360, 180, _BLUE, with_note=False)
    boxes += _chart(24, 304, 1232, 400, tuple(int(h * 0.8) for h in _BARS), _BLUE, _BLUE)
    return boxes


def render_boxes(boxes: list[Box], path: Path) -> Path:
    """Draw ``boxes`` on the page background and save the PNG."""
    image = Image.new("RGB", PAGE_SIZE, _PAGE_COLOR)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        draw.rectangle((box.x, box.y, box.x + box.w - 1, box.y + box.h - 1), fill=box.color)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def render_design(path: Path) -> Path:
    """The design image of the demo."""
    return render_boxes(reference_boxes(), path)


def page_source(boxes: list[Box]) -> str:
    """React component that draws ``boxes``, in order, on the page background."""
    rows = "\n".join(
        f"  {{ x: {b.x}, y: {b.y}, w: {b.w}, h: {b.h}, c: '{b.color}' }}," for b in boxes
    )
    width, height = PAGE_SIZE
    return f"""\
const boxes = [
{rows}
]

export default function App() {{
  return (
    <div
      style={{{{
        position: 'relative',
        width: {width},
        height: {height},
        background: '{_PAGE_COLOR}',
        overflow: 'hidden',
      }}}}
    >
      <style>{{'html,body{{margin:0}}'}}</style>
      {{boxes.map((b, i) => (
        <div
          key={{i}}
          style={{{{
            position: 'absolute',
            left: b.x,
            top: b.y,
            width: b.w,
            height: b.h,
            background: b.c,
          }}}}
        />
      ))}}
    </div>
  )
}}
"""


def _card(x: int, y: int, w: int, h: int, accent: str, *, with_note: bool) -> list[Box]:
    boxes = [
        Box(x, y, w, h, _WHITE),
        Box(x, y, w, 6, accent),
        Box(x + 24, y + 32, 120, 14, _SLATE_300),
        Box(x + 24, y + 64, 160, 36, _NAVY),
    ]
    if with_note:
        boxes.append(Box(x + 24, y + 128, 240, 12, _SLATE_200))
    return boxes


def _chart(
    x: int, y: int, w: int, h: int, bars: tuple[int, ...], color: str, last_color: str
) -> list[Box]:
    baseline = y + h - 32
    boxes = [Box(x, y, w, h, _WHITE), Box(x + 24, y + 24, 200, 16, _SLATE_300)]
    for index, height in enumerate(bars):
        bar_color = last_color if index == len(bars) - 1 else color
        boxes.append(Box(x + 24 + index * 96, baseline - height, 56, height, bar_color))
    return boxes

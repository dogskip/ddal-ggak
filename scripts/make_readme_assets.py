"""Rebuild the pictures in ``docs/assets`` from a real ``ddk demo`` run.

    uv run python scripts/make_readme_assets.py

Needs what ``ddk demo`` needs: Node.js with npm, and a Chromium (Playwright's build, Chrome or
Edge). In the terminal picture the temporary work folder is shown as ``/tmp/ddk-demo``.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.async_api import Browser, Playwright, async_playwright
from playwright.async_api import Error as PlaywrightError
from rich.cells import cell_len
from rich.console import Console
from rich.text import Text

from ddk.adapters.system_browser import find_system_browser

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"
SHOWN_FOLDER = "/tmp/ddk-demo"
ANSI = re.compile(r"\x1b\[[0-9;]*m")
CASE = "C-001"

STYLE = """
* { box-sizing: border-box; }
body { margin: 0; background: #fff; color: #1c2430;
  font: 15px/1.4 -apple-system, "Segoe UI", system-ui, sans-serif; }
figure { margin: 0; }
img { display: block; width: 100%; border: 1px solid #d5dbe3; border-radius: 8px; }
figcaption { margin-top: 8px; display: flex; gap: 8px; align-items: center; color: #5b6573; }
figcaption b { color: #1c2430; }
.pill { padding: 1px 9px; border-radius: 99px; font-size: 13px; font-weight: 600; }
.ok { background: #e3f4e8; color: #0d6b2a; }
.bad { background: #fde7e7; color: #b42318; }
"""

COMPARISON = f"""<!doctype html><meta charset="utf-8"><style>{STYLE}
main {{ width: 1100px; padding: 24px; display: grid; grid-template-columns: 1fr 1fr;
  gap: 24px 20px; }}
</style><main>{{cells}}</main>"""

PREVIEW = f"""<!doctype html><meta charset="utf-8"><style>{STYLE}
body {{ width: 1280px; height: 640px; padding: 56px; }}
h1 {{ margin: 0; font-size: 64px; letter-spacing: -1px; }}
.tagline {{ margin: 6px 0 0; font-size: 32px; font-weight: 600; }}
.what {{ margin: 12px 0 0; max-width: 900px; font-size: 20px; color: #5b6573; }}
.row {{ position: absolute; left: 56px; right: 56px; bottom: 48px; display: grid;
  grid-template-columns: repeat(3, 1fr); gap: 24px; }}
figcaption {{ font-size: 17px; }}
</style><h1>ddalggak</h1><p class="tagline">Design image in. Checked code out.</p>
<p class="what">It builds the page, type-checks and lints it, renders it in a real browser,
compares it with your design and fixes what differs, before anything touches your repo.</p>
<div class="row">{{cells}}</div>"""


def run_demo(workdir: Path) -> str:
    """Run ``ddk demo`` for real and return what it printed, colours included."""
    env = {
        **os.environ,
        "DDK_LANG": "en",
        "FORCE_COLOR": "1",
        "COLUMNS": "100",
        "TERM": "xterm-256color",
    }
    env.pop("NO_COLOR", None)
    done = subprocess.run(
        [sys.executable, "-m", "ddk", "demo", "--workdir", str(workdir)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"ddk demo failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")
    return hide_folder(done.stdout, workdir)


def hide_folder(output: str, workdir: Path) -> str:
    """Show ``SHOWN_FOLDER`` instead of the temporary folder; colour codes split the path."""
    names = sorted({str(workdir), str(workdir.resolve())}, key=len, reverse=True)
    lines: list[str] = []
    for line in output.splitlines():
        plain = ANSI.sub("", line)
        if any(name in plain for name in names):
            for name in names:
                plain = plain.replace(name, SHOWN_FOLDER)
            line = plain
        lines.append(line)
    return "\n".join(lines) + "\n"


def terminal_svg(output: str) -> str:
    """The terminal output as a picture that GitHub shows without scripts or web fonts."""
    text = Text.from_ansi(output.rstrip())
    width = max(cell_len(line) for line in text.plain.splitlines())
    console = Console(
        record=True, width=width, file=io.StringIO(), force_terminal=True, color_system="truecolor"
    )
    console.print(text, soft_wrap=True)
    return console.export_svg(title="ddk demo")


def _ssims(visual: Path) -> list[float]:
    """The SSIM of every kept round, first to last."""
    rounds = sorted(visual.glob("round-*"), key=lambda folder: int(folder.name.split("-")[1]))
    return [
        float(json.loads((folder / "report.json").read_text(encoding="utf-8"))["ssim_score"])
        for folder in rounds
    ]


def _cell(path: Path, title: str, note: str = "", tone: str = "") -> str:
    data = base64.b64encode(path.read_bytes()).decode()
    pill = f'<span class="pill {tone}">{note}</span>' if tone else f"<span>{note}</span>"
    return (
        f'<figure><img src="data:image/png;base64,{data}">'
        f"<figcaption><b>{title}</b>{pill}</figcaption></figure>"
    )


async def _launch(playwright: Playwright) -> Browser:
    configured = os.environ.get("DDK_CHROMIUM_PATH") or None
    try:
        return await playwright.chromium.launch(headless=True, executable_path=configured)
    except PlaywrightError:
        installed = find_system_browser()
        if configured or installed is None:
            raise
        return await playwright.chromium.launch(headless=True, executable_path=str(installed))


async def _shoot_html(browser: Browser, html: str, target: Path, width: int, height: int) -> None:
    page = await browser.new_page(viewport={"width": width, "height": height})
    await page.set_content(html)
    await page.screenshot(path=str(target), full_page=True)
    await page.close()


async def _shoot_report(browser: Browser, report: Path, target: Path) -> None:
    """The verdict and the screenshot checks: the top of the report, without the long tail."""
    page = await browser.new_page(viewport={"width": 1100, "height": 900})
    await page.goto(report.as_uri())
    last_check = await page.locator(".round").nth(1).bounding_box()
    assert last_check is not None
    height = int(last_check["y"] + last_check["height"] + 24)
    await page.screenshot(
        path=str(target), full_page=True, clip={"x": 0, "y": 0, "width": 1100, "height": height}
    )
    await page.close()


async def make_pictures(demo_root: Path) -> None:
    case = demo_root / "project" / ".ddk" / "cases" / CASE
    visual = case / "artifacts" / "visual"
    scores = _ssims(visual)
    first, last = scores[0], scores[-1]
    design = demo_root / "design.png"
    attempt = demo_root / "first-attempt"
    cells = [
        _cell(design, "Design", "the input image"),
        _cell(attempt / "page.png", "First attempt", f"SSIM {first:.2f} · not met", "bad"),
        _cell(attempt / "difference.png", "Difference", "red = differs from the design"),
        _cell(visual / "generated.png", "After auto-fix", f"SSIM {last:.2f} · passed", "ok"),
    ]
    row = [cells[0], cells[1], cells[3]]
    async with async_playwright() as playwright:
        browser = await _launch(playwright)
        try:
            await _shoot_html(
                browser,
                COMPARISON.replace("{cells}", "".join(cells)),
                ASSETS / "before-after.png",
                1100,
                800,
            )
            await _shoot_html(
                browser,
                PREVIEW.replace("{cells}", "".join(row)),
                ASSETS / "social-preview.png",
                1280,
                640,
            )
            await _shoot_report(browser, case / "reports" / "report.html", ASSETS / "report.png")
        finally:
            await browser.close()


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ddk-assets-") as scratch:
        demo_root = Path(scratch) / "demo"
        output = run_demo(demo_root)
        (ASSETS / "demo.svg").write_text(terminal_svg(output), encoding="utf-8")
        asyncio.run(make_pictures(demo_root))
    for name in ("demo.svg", "before-after.png", "social-preview.png", "report.png"):
        print(f"{ASSETS / name}  {(ASSETS / name).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

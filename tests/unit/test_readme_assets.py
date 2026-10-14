"""The README overview keeps diagnostic overlays separate from the result."""

from __future__ import annotations

import base64
import importlib.util
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts/make_readme_assets.py"
_SPEC = importlib.util.spec_from_file_location("readme_assets", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
assets = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(assets)


@pytest.mark.asyncio
async def test_overview_contains_only_reference_first_attempt_and_repaired_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = tmp_path / "demo"
    visual = demo / "project/.ddk/cases/C-001/artifacts/visual"
    paths = [
        demo / "design.png",
        demo / "first-attempt/page.png",
        demo / "first-attempt/difference.png",
        visual / "generated.png",
    ]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes([index]))
    shots: list[tuple[str, Path, int, int]] = []

    async def capture(_browser: object, html: str, target: Path, width: int, height: int) -> None:
        shots.append((html, target, width, height))

    browser = AsyncMock()
    monkeypatch.setattr(assets, "_ssims", lambda _path: [0.89, 1.0])
    monkeypatch.setattr(assets, "_launch", AsyncMock(return_value=browser))
    monkeypatch.setattr(assets, "_shoot_html", capture)
    monkeypatch.setattr(assets, "_shoot_report", AsyncMock())

    await assets.make_pictures(demo)

    overview = shots[0][0]
    assert overview.count("<figure>") == 3
    assert "Difference" not in overview
    assert "schematic" in overview
    assert (
        overview.index("Design")
        < overview.index("First attempt")
        < overview.index("After auto-fix")
    )
    assert "0.89" in overview and "1.00" in overview
    encoded = re.findall(r'src="data:image/png;base64,([^\"]+)"', overview)
    expected = [paths[index].read_bytes() for index in (0, 1, 3)]
    assert [base64.b64decode(value) for value in encoded] == expected
    assert any(
        target.name == "before-after-mobile.png" and width <= 600
        for _html, target, width, _height in shots
    )
    browser.close.assert_awaited_once()

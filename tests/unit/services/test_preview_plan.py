"""plan_preview: which command serves the built app, decided from the project's own files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddk.services.toolchain import plan_preview


def _project(
    tmp_path: Path, *, deps: dict[str, str] | None = None, bins: tuple[str, ...] = ()
) -> Path:
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "app", "devDependencies": deps or {}}), encoding="utf-8"
    )
    for name in bins:
        binary = tmp_path / "node_modules" / ".bin" / name
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text("#!/bin/sh\n", encoding="utf-8")
    return tmp_path


class TestSupported:
    def test_vite_project_uses_vite_preview_on_loopback(self, tmp_path: Path) -> None:
        plan = plan_preview(_project(tmp_path, deps={"vite": "^7"}, bins=("vite",)))

        assert plan.command == [
            "npm", "exec", "--no", "--", "vite", "preview",
            "--host", "127.0.0.1", "--port", "{port}", "--strictPort",
        ]  # fmt: skip
        assert plan.reason == ""

    def test_next_project_uses_next_start(self, tmp_path: Path) -> None:
        plan = plan_preview(_project(tmp_path, deps={"next": "15"}, bins=("next",)))

        assert plan.command == [
            "npm", "exec", "--no", "--", "next", "start",
            "--hostname", "127.0.0.1", "--port", "{port}",
        ]  # fmt: skip

    def test_astro_project_uses_astro_preview(self, tmp_path: Path) -> None:
        plan = plan_preview(_project(tmp_path, deps={"astro": "5"}, bins=("astro",)))

        assert plan.command is not None
        assert plan.command[4:6] == ["astro", "preview"]


class TestNotSupported:
    def test_no_package_json(self, tmp_path: Path) -> None:
        plan = plan_preview(tmp_path)

        assert plan.command is None
        assert "package.json" in plan.reason

    def test_unknown_framework_is_reported_not_guessed(self, tmp_path: Path) -> None:
        plan = plan_preview(
            _project(tmp_path, deps={"react-scripts": "5"}, bins=("react-scripts",))
        )

        assert plan.command is None
        assert "vite" in plan.reason and "next" in plan.reason

    def test_declared_but_not_installed_tool(self, tmp_path: Path) -> None:
        plan = plan_preview(_project(tmp_path, deps={"vite": "^7"}))

        assert plan.command is None
        assert "vite" in plan.reason and "not installed" in plan.reason

    @pytest.mark.parametrize("raw", ["{broken", "[]", '"text"'])
    def test_unreadable_package_json(self, tmp_path: Path, raw: str) -> None:
        (tmp_path / "package.json").write_text(raw, encoding="utf-8")

        assert plan_preview(tmp_path).command is None

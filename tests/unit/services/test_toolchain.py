"""Toolchain planner tests — decides which validation steps apply to a project."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ddk.services.toolchain import ToolchainPlan, plan_toolchain


def _project(
    root: Path,
    *,
    scripts: dict[str, str] | None = None,
    dev_dependencies: dict[str, str] | None = None,
    dependencies: dict[str, str] | None = None,
    files: dict[str, str] | None = None,
    installed: bool = True,
    extra: dict[str, Any] | None = None,
) -> Path:
    package: dict[str, Any] = {"name": "app"}
    if scripts is not None:
        package["scripts"] = scripts
    if dev_dependencies is not None:
        package["devDependencies"] = dev_dependencies
    if dependencies is not None:
        package["dependencies"] = dependencies
    package.update(extra or {})
    (root / "package.json").write_text(json.dumps(package), encoding="utf-8")
    for name, content in (files or {}).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if installed:
        (root / "node_modules" / ".bin").mkdir(parents=True, exist_ok=True)
    return root


def _commands(plan: ToolchainPlan) -> dict[str, list[list[str]]]:
    grouped: dict[str, list[list[str]]] = {}
    for step in plan.steps:
        grouped.setdefault(step.name, []).append(step.command)
    return grouped


class TestStepSelection:
    def test_build_script_typescript_and_eslint_give_three_step_kinds(self, tmp_path: Path) -> None:
        _project(
            tmp_path,
            scripts={"build": "vite build"},
            dev_dependencies={"typescript": "^5", "eslint": "^9"},
            files={"tsconfig.json": "{}", "eslint.config.js": "export default []"},
        )

        plan = plan_toolchain(tmp_path)

        assert _commands(plan) == {
            "build": [["npm", "run", "build"]],
            "typecheck": [["npm", "exec", "--no", "--", "tsc", "--noEmit"]],
            "lint": [["npm", "exec", "--no", "--", "eslint", "."]],
        }
        assert plan.skipped == []

    def test_no_package_json_means_nothing_applies(self, tmp_path: Path) -> None:
        plan = plan_toolchain(tmp_path)

        assert plan.steps == []
        assert {s.name for s in plan.skipped} == {"build", "typecheck", "lint"}
        assert all("package.json" in s.reason for s in plan.skipped)

    def test_missing_build_script_is_reported_not_guessed(self, tmp_path: Path) -> None:
        _project(tmp_path, scripts={"dev": "vite"})

        plan = plan_toolchain(tmp_path)

        assert "build" not in _commands(plan)
        assert any(s.name == "build" and "build" in s.reason for s in plan.skipped)

    def test_lint_without_eslint_config_is_skipped(self, tmp_path: Path) -> None:
        _project(tmp_path, dev_dependencies={"eslint": "^9"})

        plan = plan_toolchain(tmp_path)

        assert any(s.name == "lint" and "ESLint" in s.reason for s in plan.skipped)

    def test_project_lint_script_wins_over_default_eslint_call(self, tmp_path: Path) -> None:
        _project(tmp_path, scripts={"lint": "eslint . --max-warnings 0"})

        assert _commands(plan_toolchain(tmp_path))["lint"] == [["npm", "run", "lint"]]

    def test_project_typecheck_script_wins(self, tmp_path: Path) -> None:
        _project(
            tmp_path,
            scripts={"typecheck": "tsc -p . --noEmit"},
            files={"tsconfig.json": "{}"},
        )

        assert _commands(plan_toolchain(tmp_path))["typecheck"] == [["npm", "run", "typecheck"]]

    def test_typescript_not_declared_skips_typecheck(self, tmp_path: Path) -> None:
        _project(tmp_path, files={"tsconfig.json": "{}"}, installed=False)

        plan = plan_toolchain(tmp_path)

        assert any(s.name == "typecheck" and "typescript" in s.reason.lower() for s in plan.skipped)


class TestSolutionStyleTsconfig:
    def test_references_are_checked_one_by_one(self, tmp_path: Path) -> None:
        # Vite's default template: root tsconfig only lists references, so a bare
        # `tsc --noEmit` there exits 0 without checking a single file.
        _project(
            tmp_path,
            dev_dependencies={"typescript": "^5"},
            files={
                "tsconfig.json": json.dumps(
                    {
                        "files": [],
                        "references": [
                            {"path": "./tsconfig.app.json"},
                            {"path": "./tsconfig.node.json"},
                        ],
                    }
                ),
                "tsconfig.app.json": "{}",
                "tsconfig.node.json": "{}",
            },
        )

        assert _commands(plan_toolchain(tmp_path))["typecheck"] == [
            ["npm", "exec", "--no", "--", "tsc", "--noEmit", "-p", "tsconfig.app.json"],
            ["npm", "exec", "--no", "--", "tsc", "--noEmit", "-p", "tsconfig.node.json"],
        ]

    def test_jsonc_comments_and_trailing_commas_are_tolerated(self, tmp_path: Path) -> None:
        _project(
            tmp_path,
            dev_dependencies={"typescript": "^5"},
            files={
                "tsconfig.json": (
                    "{\n"
                    "  // solution style\n"
                    '  "files": [],\n'
                    '  "references": [ {"path": "./tsconfig.app.json"}, ], /* trailing */\n'
                    "}\n"
                ),
                "tsconfig.app.json": "{}",
            },
        )

        assert _commands(plan_toolchain(tmp_path))["typecheck"] == [
            ["npm", "exec", "--no", "--", "tsc", "--noEmit", "-p", "tsconfig.app.json"],
        ]

    def test_reference_to_a_missing_project_is_ignored(self, tmp_path: Path) -> None:
        _project(
            tmp_path,
            dev_dependencies={"typescript": "^5"},
            files={
                "tsconfig.json": json.dumps(
                    {"files": [], "references": [{"path": "./gone"}, {"path": "./real"}]}
                ),
                "real/tsconfig.json": "{}",
            },
        )

        assert _commands(plan_toolchain(tmp_path))["typecheck"] == [
            ["npm", "exec", "--no", "--", "tsc", "--noEmit", "-p", "real"],
        ]


class TestPackageManagerAndInstall:
    def test_lockfile_decides_the_package_manager(self, tmp_path: Path) -> None:
        _project(tmp_path, scripts={"build": "vite build"}, files={"pnpm-lock.yaml": ""})

        plan = plan_toolchain(tmp_path)

        assert plan.package_manager == "pnpm"
        assert _commands(plan)["build"] == [["pnpm", "run", "build"]]

    def test_installed_project_needs_no_install(self, tmp_path: Path) -> None:
        _project(tmp_path, dependencies={"react": "^19"})

        plan = plan_toolchain(tmp_path)

        assert plan.needs_install is False

    def test_missing_node_modules_needs_install_without_running_scripts(
        self, tmp_path: Path
    ) -> None:
        _project(
            tmp_path,
            dependencies={"react": "^19"},
            files={"package-lock.json": "{}"},
            installed=False,
        )

        plan = plan_toolchain(tmp_path)

        assert plan.needs_install is True
        assert plan.install_command == [
            "npm",
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]

    def test_no_lockfile_falls_back_to_plain_install(self, tmp_path: Path) -> None:
        _project(tmp_path, dependencies={"react": "^19"}, installed=False)

        plan = plan_toolchain(tmp_path)

        assert plan.install_command is not None
        assert plan.install_command[:2] == ["npm", "install"]
        assert "--ignore-scripts" in plan.install_command

    def test_project_without_dependencies_never_needs_install(self, tmp_path: Path) -> None:
        _project(tmp_path, installed=False)

        assert plan_toolchain(tmp_path).needs_install is False

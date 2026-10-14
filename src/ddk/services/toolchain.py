"""Toolchain planner — which build / type-check / lint steps apply to a JS/TS project.

Reads only the project's own files (package.json, lockfiles, tsconfig, ESLint config).
Never runs anything and never guesses: a step with no matching setup is reported as
skipped with the reason, so "nothing was verified" stays visible downstream.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

StepName = Literal["build", "typecheck", "lint"]

_TYPECHECK_SCRIPTS = ("typecheck", "type-check", "check-types", "tsc")
_ESLINT_CONFIGS = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    "eslint.config.ts",
    "eslint.config.mts",
    "eslint.config.cts",
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
)
_LOCKFILES: tuple[tuple[str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "yarn"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
    ("package-lock.json", "npm"),
)
_LOCAL_BIN = ["npm", "exec", "--no", "--"]


@dataclass(frozen=True)
class ToolStep:
    """One command the validator should run."""

    name: StepName
    command: list[str]

    @property
    def label(self) -> str:
        return " ".join(self.command)


@dataclass(frozen=True)
class SkippedStep:
    """A step that does not apply to this project, with the reason."""

    name: StepName
    reason: str


@dataclass(frozen=True)
class ToolchainPlan:
    package_manager: str
    needs_install: bool
    install_command: list[str] | None
    steps: list[ToolStep] = field(default_factory=lambda: list[ToolStep]())
    skipped: list[SkippedStep] = field(default_factory=lambda: list[SkippedStep]())


@dataclass(frozen=True)
class PreviewPlan:
    """How to serve the built app; ``command`` is ``None`` (with ``reason``) when it cannot be."""

    command: list[str] | None
    reason: str = ""


# framework package -> arguments after `npm exec --no -- <tool>`
_PREVIEW_COMMANDS: dict[str, list[str]] = {
    "vite": ["preview", "--host", "127.0.0.1", "--port", "{port}", "--strictPort"],
    "next": ["start", "--hostname", "127.0.0.1", "--port", "{port}"],
    "astro": ["preview", "--host", "127.0.0.1", "--port", "{port}"],
}


def plan_preview(project_dir: Path) -> PreviewPlan:
    """Command that serves the built app on loopback, with ``{port}`` left to fill in."""
    package_path = project_dir / "package.json"
    if not package_path.is_file():
        return PreviewPlan(None, "package.json not found")
    declared = _declared_packages(_load_jsonc(package_path))
    for tool, arguments in _PREVIEW_COMMANDS.items():
        if tool not in declared:
            continue
        if not (project_dir / "node_modules" / ".bin" / tool).exists():
            return PreviewPlan(None, f"{tool} is declared but not installed in node_modules")
        return PreviewPlan([*_LOCAL_BIN, tool, *arguments])
    return PreviewPlan(None, "no preview command for this project (supported: vite, next, astro)")


def plan_toolchain(project_dir: Path) -> ToolchainPlan:
    """Decide which validation steps apply to ``project_dir``."""
    package_path = project_dir / "package.json"
    if not package_path.is_file():
        reason = "package.json not found"
        return ToolchainPlan(
            package_manager="npm",
            needs_install=False,
            install_command=None,
            skipped=[SkippedStep(name, reason) for name in ("build", "typecheck", "lint")],
        )

    package = _load_jsonc(package_path)
    manager = _package_manager(project_dir, package)
    scripts = _string_map(package.get("scripts"))
    declared = _declared_packages(package)
    steps: list[ToolStep] = []
    skipped: list[SkippedStep] = []

    if "build" in scripts:
        steps.append(ToolStep("build", [manager, "run", "build"]))
    else:
        skipped.append(SkippedStep("build", "no build script in package.json"))

    typecheck, why_not = _typecheck_steps(project_dir, manager, scripts, declared)
    steps.extend(typecheck)
    if not typecheck:
        skipped.append(SkippedStep("typecheck", why_not))

    lint, why_not = _lint_step(project_dir, manager, package, scripts, declared)
    if lint is not None:
        steps.append(lint)
    else:
        skipped.append(SkippedStep("lint", why_not))

    needs_install = bool(declared) and not (project_dir / "node_modules").is_dir()
    return ToolchainPlan(
        package_manager=manager,
        needs_install=needs_install,
        install_command=_install_command(project_dir, manager) if needs_install else None,
        steps=steps,
        skipped=skipped,
    )


def _typecheck_steps(
    project_dir: Path,
    manager: str,
    scripts: dict[str, str],
    declared: set[str],
) -> tuple[list[ToolStep], str]:
    for script in _TYPECHECK_SCRIPTS:
        if script in scripts:
            return [ToolStep("typecheck", [manager, "run", script])], ""

    tsconfig_path = project_dir / "tsconfig.json"
    if not tsconfig_path.is_file():
        return [], "no tsconfig.json"
    if "typescript" not in declared and not (project_dir / "node_modules/.bin/tsc").exists():
        return [], "typescript is not a dependency of this project"

    tsc = [*_LOCAL_BIN, "tsc", "--noEmit"]
    config = _load_jsonc(tsconfig_path)
    references = _reference_paths(project_dir, config)
    solution_style = not config.get("files") and not config.get("include")
    if references and solution_style:
        return [ToolStep("typecheck", [*tsc, "-p", ref]) for ref in references], ""
    if solution_style and "references" in config:
        return [], "tsconfig.json only lists references that do not exist"
    return [ToolStep("typecheck", tsc)], ""


def _lint_step(
    project_dir: Path,
    manager: str,
    package: dict[str, Any],
    scripts: dict[str, str],
    declared: set[str],
) -> tuple[ToolStep | None, str]:
    if "lint" in scripts:
        return ToolStep("lint", [manager, "run", "lint"]), ""

    has_config = "eslintConfig" in package or any(
        (project_dir / name).is_file() for name in _ESLINT_CONFIGS
    )
    if not has_config:
        return None, "no ESLint configuration found"
    if "eslint" not in declared and not (project_dir / "node_modules/.bin/eslint").exists():
        return None, "eslint is not a dependency of this project"
    return ToolStep("lint", [*_LOCAL_BIN, "eslint", "."]), ""


def _reference_paths(project_dir: Path, config: dict[str, Any]) -> list[str]:
    raw = config.get("references")
    if not isinstance(raw, list):
        return []
    found: list[str] = []
    for item in cast("list[object]", raw):
        if not isinstance(item, dict):
            continue
        path = cast("dict[str, Any]", item).get("path")
        if not isinstance(path, str):
            continue
        normalized = os.path.normpath(path).replace("\\", "/")
        target = project_dir / normalized
        if target.is_file() or (target.is_dir() and (target / "tsconfig.json").is_file()):
            found.append(normalized)
    return found


def _package_manager(project_dir: Path, package: dict[str, Any]) -> str:
    declared = package.get("packageManager")
    if isinstance(declared, str):
        name = declared.split("@", 1)[0]
        if name in {"npm", "pnpm", "yarn", "bun"}:
            return name
    for lockfile, manager in _LOCKFILES:
        if (project_dir / lockfile).exists():
            return manager
    return "npm"


def _install_command(project_dir: Path, manager: str) -> list[str]:
    locked = any(
        (project_dir / lockfile).exists() for lockfile, name in _LOCKFILES if name == manager
    )
    if manager == "pnpm":
        flags = ["--frozen-lockfile"] if locked else []
        return ["pnpm", "install", *flags, "--ignore-scripts"]
    if manager == "yarn":
        if (project_dir / ".yarnrc.yml").exists():
            return ["yarn", "install", *(["--immutable"] if locked else [])]
        return ["yarn", "install", *(["--frozen-lockfile"] if locked else []), "--ignore-scripts"]
    if manager == "bun":
        flags = ["--frozen-lockfile"] if locked else []
        return ["bun", "install", *flags, "--ignore-scripts"]
    verb = "ci" if locked else "install"
    return ["npm", verb, "--ignore-scripts", "--no-audit", "--no-fund"]


def _declared_packages(package: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("dependencies", "devDependencies", "optionalDependencies"):
        names.update(_string_map(package.get(key)))
    return names


def _string_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(k): str(v) for k, v in cast("dict[object, object]", value).items() if isinstance(v, str)
    }


def _load_jsonc(path: Path) -> dict[str, Any]:
    """Load JSON that may contain ``//`` / ``/* */`` comments and trailing commas."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = json.loads(_strip_jsonc(text))
    except ValueError:
        return {}
    return cast("dict[str, Any]", data) if isinstance(data, dict) else {}


def _strip_jsonc(text: str) -> str:
    out: list[str] = []
    last_significant = -1
    i = 0
    in_string = False
    while i < len(text):
        char = text[i]
        pair = text[i : i + 2]
        if in_string:
            out.append(char)
            if char == "\\" and i + 1 < len(text):
                out.append(text[i + 1])
                i += 1
            elif char == '"':
                in_string = False
        elif pair == "//":
            newline = text.find("\n", i)
            i = len(text) if newline < 0 else newline - 1
        elif pair == "/*":
            end = text.find("*/", i + 2)
            i = len(text) if end < 0 else end + 1
        else:
            if char == '"':
                in_string = True
            elif char in "}]" and last_significant >= 0 and out[last_significant] == ",":
                out[last_significant] = ""
            out.append(char)
            if not char.isspace():
                last_significant = len(out) - 1
        i += 1
    return "".join(out)

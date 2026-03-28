"""RepoConventionScanner — static-first repo analysis + LLM supplement (INGEST-03, D-07)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.repo import (
    DesignTokens,
    FileLayoutRules,
    NamingRules,
    RepoProfile,
)


class RepoConventionScanner:
    """Static-first repo analysis. LLM (haiku) supplements only when static is insufficient."""

    def __init__(self, llm: LLMAdapter | None = None) -> None:
        self._llm = llm

    async def scan(self, repo_path: Path) -> RepoProfile:
        """Analyze repo conventions. Static parsing first, LLM only if needed (D-07)."""
        profile = self._static_scan(repo_path)
        if self._needs_llm_supplement(profile) and self._llm is not None:
            profile = await self._llm_supplement(profile, repo_path)
        return profile

    def _static_scan(self, repo_path: Path) -> RepoProfile:
        pkg = self._parse_package_json(repo_path / "package.json")
        ts_config = self._parse_tsconfig(repo_path / "tsconfig.json")
        framework = self._detect_framework(pkg)
        language: str = (
            "typescript"
            if ts_config or (repo_path / "tsconfig.json").exists()
            else "javascript"
        )
        css_approach = self._detect_css_approach(pkg)
        package_manager = self._detect_package_manager(repo_path)
        build_tool = self._detect_build_tool(pkg)
        component_library = self._detect_component_library(pkg)
        test_runner = self._detect_test_runner(pkg)
        naming_rules = self._infer_naming_rules(repo_path)
        file_layout = self._infer_file_layout(repo_path)
        existing = self._find_existing_components(repo_path)

        return RepoProfile(
            framework=framework,  # type: ignore[arg-type]
            language=language,  # type: ignore[arg-type]
            package_manager=package_manager,  # type: ignore[arg-type]
            css_approach=css_approach,  # type: ignore[arg-type]
            component_library=component_library,
            test_runner=test_runner,
            build_tool=build_tool,
            naming_rules=naming_rules,
            file_layout=file_layout,
            design_tokens=DesignTokens(),
            existing_components=existing,
        )

    # --- Static parsing helpers ---

    def _parse_package_json(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _parse_tsconfig(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _parse_prettierrc(self, repo_path: Path) -> dict[str, Any]:
        for name in (".prettierrc", ".prettierrc.json"):
            p = repo_path / name
            if p.exists():
                try:
                    return json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
        return {}

    def _detect_framework(self, pkg: dict[str, Any]) -> str:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "next" in deps:
            return "next"
        if "nuxt" in deps:
            return "nuxt"
        if "@angular/core" in deps:
            return "angular"
        if "react" in deps:
            return "react"
        if "vue" in deps:
            return "vue"
        if "svelte" in deps:
            return "svelte"
        return "other"

    def _detect_css_approach(self, pkg: dict[str, Any]) -> str:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "tailwindcss" in deps:
            return "tailwind"
        if "styled-components" in deps:
            return "styled-components"
        if "@emotion/react" in deps:
            return "emotion"
        if "sass" in deps or "scss" in deps:
            return "scss"
        return "other"

    def _detect_package_manager(self, repo_path: Path) -> str:
        if (repo_path / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (repo_path / "yarn.lock").exists():
            return "yarn"
        if (repo_path / "bun.lockb").exists():
            return "bun"
        return "npm"

    def _detect_build_tool(self, pkg: dict[str, Any]) -> str:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vite" in deps or "@vitejs/plugin-react" in deps:
            return "vite"
        if "webpack" in deps:
            return "webpack"
        return "vite"

    def _detect_component_library(self, pkg: dict[str, Any]) -> str | None:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for lib in (
            "@radix-ui/react-dialog",
            "@mui/material",
            "antd",
            "@chakra-ui/react",
            "@mantine/core",
        ):
            if lib in deps:
                return lib.split("/")[0] if "/" in lib else lib
        return None

    def _detect_test_runner(self, pkg: dict[str, Any]) -> str | None:
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vitest" in deps:
            return "vitest"
        if "jest" in deps:
            return "jest"
        return None

    def _infer_naming_rules(self, repo_path: Path) -> NamingRules:
        return NamingRules()  # defaults; LLM supplement refines if needed

    def _infer_file_layout(self, repo_path: Path) -> FileLayoutRules:
        layout = FileLayoutRules()
        src = repo_path / "src"
        if src.exists():
            for d in ("components", "pages", "hooks", "utils", "types", "styles"):
                if (src / d).exists():
                    setattr(layout, f"{d}_dir", f"src/{d}")
        return layout

    def _find_existing_components(self, repo_path: Path) -> list[str]:
        comps: list[str] = []
        src = repo_path / "src"
        if src.exists():
            for f in sorted(src.rglob("*.tsx")):
                comps.append(str(f.relative_to(repo_path)))
        return comps[:50]  # cap at 50

    # --- LLM supplement ---

    def _needs_llm_supplement(self, profile: RepoProfile) -> bool:
        """LLM supplement needed only when static analysis cannot determine framework (D-07)."""
        return profile.framework == "other"

    async def _llm_supplement(self, profile: RepoProfile, repo_path: Path) -> RepoProfile:
        """Call haiku to infer naming conventions and patterns not found statically."""
        assert self._llm is not None
        file_tree = self._sample_file_tree(repo_path, max_paths=50)
        system_prompt = (
            "You are a senior front-end developer analyzing a repository structure.\n"
            "Extract naming conventions and component patterns.\n"
            "Output JSON with keys: component_pattern, file_pattern.\n"
            "component_pattern: PascalCase or kebab-case\n"
            "file_pattern: PascalCase, kebab-case, or camelCase"
        )
        user_msg = f"File tree:\n{file_tree}\n\nDetected framework: {profile.framework}"
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_msg),
        ]
        config = LLMCallConfig(
            model="claude-3-haiku-20240307",
            temperature=0.0,
            max_tokens=512,
        )
        response = await self._llm.complete(messages, config)
        try:
            data = json.loads(response.content)
            if "component_pattern" in data:
                valid_patterns = ("PascalCase", "kebab-case")
                if data["component_pattern"] in valid_patterns:
                    profile.naming_rules.component_pattern = data["component_pattern"]
            if "file_pattern" in data:
                valid_file = ("PascalCase", "kebab-case", "camelCase")
                if data["file_pattern"] in valid_file:
                    profile.naming_rules.file_pattern = data["file_pattern"]
        except (json.JSONDecodeError, KeyError):
            pass  # static result is fine
        return profile

    def _sample_file_tree(self, repo_path: Path, max_paths: int = 50) -> str:
        paths: list[str] = []
        for p in sorted(repo_path.rglob("*")):
            if p.is_file() and "node_modules" not in str(p) and "__pycache__" not in str(p):
                paths.append(str(p.relative_to(repo_path)))
                if len(paths) >= max_paths:
                    break
        return "\n".join(paths)

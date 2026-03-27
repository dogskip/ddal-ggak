from __future__ import annotations

from typing import Literal

from pydantic import Field

from ._base import DDKBaseModel


class NamingRules(DDKBaseModel):
    component_pattern: Literal["PascalCase", "kebab-case"] = "PascalCase"
    file_pattern: Literal["PascalCase", "kebab-case", "camelCase"] = "kebab-case"
    hook_prefix: str = "use"
    test_suffix: str = ".test"
    story_suffix: str = ".stories"
    style_suffix: str = ".module.css"


class FileLayoutRules(DDKBaseModel):
    components_dir: str = "src/components"
    pages_dir: str = "src/pages"
    hooks_dir: str = "src/hooks"
    utils_dir: str = "src/utils"
    types_dir: str = "src/types"
    styles_dir: str = "src/styles"
    test_co_location: bool = True  # 컴포넌트 옆에 테스트 파일


class DesignTokens(DDKBaseModel):
    colors: dict[str, str] = Field(default_factory=dict)
    # {"primary": "#3B82F6", "secondary": "#6B7280", ...}
    spacing: dict[str, str] = Field(default_factory=dict)
    # {"xs": "0.25rem", "sm": "0.5rem", "md": "1rem", ...}
    typography: dict[str, dict] = Field(default_factory=dict)
    # {"heading1": {"size": "2rem", "weight": "700"}, ...}
    breakpoints: dict[str, str] = Field(default_factory=dict)
    # {"sm": "640px", "md": "768px", "lg": "1024px", ...}
    border_radius: dict[str, str] = Field(default_factory=dict)


class RepoProfile(DDKBaseModel):
    framework: Literal["react", "vue", "svelte", "next", "nuxt", "angular", "other"]
    language: Literal["typescript", "javascript"] = "typescript"
    package_manager: Literal["npm", "yarn", "pnpm", "bun"] = "pnpm"
    css_approach: Literal[
        "tailwind", "css-modules", "styled-components", "emotion", "scss", "other"
    ] = "tailwind"
    component_library: str | None = None
    # "shadcn/ui", "radix-ui", "mui", "antd", "chakra", "mantine" 등
    test_runner: str | None = None  # "vitest", "jest"
    build_tool: str = "vite"
    node_version: str | None = None  # "20", "22" 등
    naming_rules: NamingRules = Field(default_factory=NamingRules)
    file_layout: FileLayoutRules = Field(default_factory=FileLayoutRules)
    design_tokens: DesignTokens = Field(default_factory=DesignTokens)
    existing_components: list[str] = Field(default_factory=list)
    # 재사용 가능 컴포넌트 경로 목록

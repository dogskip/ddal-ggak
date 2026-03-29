"""DesignSystemInferencer — LLM-powered design token inference (INGEST-05)."""

from __future__ import annotations

import base64
import json
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models.design_system import DesignSystem
from ddk.models.input import CaseInput
from ddk.models.repo import DesignTokens, RepoProfile

# System prompt — starts with "Analyze" (key="analyze") to avoid FakeLLMAdapter
# collision with SemanticIntentExtractor (key="you")
_SYSTEM_PROMPT = """Analyze UI screenshots and repository convention data
to infer a complete design system.

You must output a valid JSON object conforming to the DesignSystem schema.
Do not include any explanation outside the JSON.

## DesignSystem Rules

### Token categories
- **color**: Named color values (hex, rgb, hsl). Prefer semantic names:
  "primary", "secondary", "danger", "success", "neutral-100" etc.
- **spacing**: Size/gap values in rem or px. Use T-shirt size names:
  "xs", "sm", "md", "lg", "xl", "2xl" etc.
- **typography**: Font size values in rem or px. Use semantic names:
  "body", "caption", "heading1", "heading2" etc.
- **border_radius**: Border radius values. Use names like "none", "sm", "md", "lg", "full".
- **breakpoint**: Responsive breakpoints in px. Use names like "sm", "md", "lg", "xl".

### Token confidence scoring
- 1.0 = clearly visible/consistent pattern in the design
- 0.7~0.9 = probable based on context
- <0.7 = uncertain — only include if clearly identifiable

### primitive_components
List PascalCase component type names that appear as reusable UI primitives.
Examples: ["Button", "Input", "Card", "Badge", "Avatar", "Icon", "Spinner"]

### token_source
- "static": tokens came from config files only
- "llm": tokens inferred from screenshots/analysis
- "hybrid": combination of both

## Critical constraints
- Only include tokens that are clearly identifiable from the provided input.
- Do NOT hallucinate token values not visible in the screenshots.
- Maximum 50 tokens total across all categories."""

_MEDIA_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class DesignSystemInferencer:
    """Infers DesignSystem tokens from screenshots and repo analysis (sonnet)."""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=4096,
        )

    async def infer(self, case_input: CaseInput, repo_profile: RepoProfile) -> DesignSystem:
        """Infer design system tokens from screenshots and repo conventions.

        Args:
            case_input: Contains image_paths, prompt, case_id.
            repo_profile: Existing repo profile with framework/style info.

        Returns:
            Validated DesignSystem with inferred tokens and primitive components.
        """
        # Build images list from case_input
        images: list[tuple[str, str]] = []
        for image_path in case_input.image_paths:
            image_bytes = image_path.read_bytes()
            image_b64 = base64.standard_b64encode(image_bytes).decode()
            suffix = image_path.suffix.lower()
            media_type = _MEDIA_TYPES.get(suffix, "image/png")
            images.append((image_b64, media_type))

        user_content = (
            f"Analyze these UI screenshots and extract the design system tokens.\n\n"
            f"Repository framework: {repo_profile.framework}\n"
            f"CSS approach: {repo_profile.css_approach}\n"
        )
        if repo_profile.component_library:
            user_content += f"Component library: {repo_profile.component_library}\n"
        user_content += (
            f"\nUser's design intent: {case_input.prompt}\n\n"
            "Output the complete DesignSystem JSON object with all inferred tokens."
        )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(
                role="user",
                content=user_content,
                images=images if images else None,
            ),
        ]

        response: LLMResponse = await self._llm.complete_structured(
            messages, self._config, output_schema=DesignSystem
        )

        data: dict[str, Any] = json.loads(response.content)
        # Always inject our case_id — never trust LLM to set this correctly
        data["case_id"] = case_input.case_id
        data.setdefault("inferred_tokens", [])
        data.setdefault("primitive_components", [])
        data.setdefault("token_source", "llm")

        return DesignSystem.model_validate(data)

    def enrich_profile(self, design_system: DesignSystem, repo_profile: RepoProfile) -> RepoProfile:
        """Enrich a RepoProfile's design_tokens with inferred DesignSystem tokens.

        Returns a new RepoProfile (immutable — does not mutate the original).

        Args:
            design_system: Inferred design system from ``infer()``.
            repo_profile: Existing repo profile to enrich.

        Returns:
            New RepoProfile with populated design_tokens field.
        """
        colors: dict[str, str] = dict(repo_profile.design_tokens.colors)
        spacing: dict[str, str] = dict(repo_profile.design_tokens.spacing)
        typography: dict[str, dict[str, str]] = {
            k: dict(v) for k, v in repo_profile.design_tokens.typography.items()
        }
        border_radius: dict[str, str] = dict(repo_profile.design_tokens.border_radius)
        breakpoints: dict[str, str] = dict(repo_profile.design_tokens.breakpoints)

        for token in design_system.inferred_tokens:
            if token.category == "color":
                colors[token.name] = token.value
            elif token.category == "spacing":
                spacing[token.name] = token.value
            elif token.category == "typography":
                typography[token.name] = {"value": token.value}
            elif token.category == "border_radius":
                border_radius[token.name] = token.value
            elif token.category == "breakpoint":
                breakpoints[token.name] = token.value

        enriched_tokens = DesignTokens(
            colors=colors,
            spacing=spacing,
            typography=typography,
            border_radius=border_radius,
            breakpoints=breakpoints,
        )
        return repo_profile.model_copy(update={"design_tokens": enriched_tokens})

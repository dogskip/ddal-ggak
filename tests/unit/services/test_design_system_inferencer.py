"""Unit tests for DesignSystemInferencer (INGEST-05)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddk.models.design_system import DesignSystem
from ddk.models.input import CaseInput
from ddk.models.repo import RepoProfile
from ddk.services.design_system_inferencer import DesignSystemInferencer, _SYSTEM_PROMPT
from tests.fakes.fake_llm_adapter import FakeLLMAdapter


@pytest.fixture
def mock_design_system_json() -> str:
    return json.dumps(
        {
            "case_id": "will-be-overwritten",
            "inferred_tokens": [
                {"name": "primary", "value": "#3B82F6", "category": "color", "confidence": 0.95},
                {"name": "secondary", "value": "#6B7280", "category": "color", "confidence": 0.9},
                {"name": "sm", "value": "0.5rem", "category": "spacing", "confidence": 0.9},
                {"name": "md", "value": "1rem", "category": "spacing", "confidence": 0.9},
                {"name": "heading1", "value": "2rem", "category": "typography", "confidence": 0.85},
                {"name": "rounded", "value": "0.25rem", "category": "border_radius", "confidence": 0.8},
                {"name": "lg", "value": "1024px", "category": "breakpoint", "confidence": 0.9},
            ],
            "primitive_components": ["Button", "Card", "Badge"],
            "token_source": "llm",
        }
    )


@pytest.fixture
def case_input(tmp_path: Path) -> CaseInput:
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 50)
    return CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="쇼핑몰 페이지 디자인",
        repo_path=tmp_path,
    )


@pytest.fixture
def repo_profile() -> RepoProfile:
    return RepoProfile(framework="react")


class TestDesignSystemInferencer:
    async def test_infer_returns_design_system(
        self,
        case_input: CaseInput,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"analyze": mock_design_system_json})
        inferencer = DesignSystemInferencer(llm=fake_llm)
        result = await inferencer.infer(case_input, repo_profile)
        assert isinstance(result, DesignSystem)
        assert result.case_id == "C-001"
        assert len(result.inferred_tokens) == 7

    async def test_infer_sets_case_id(
        self,
        case_input: CaseInput,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"analyze": mock_design_system_json})
        inferencer = DesignSystemInferencer(llm=fake_llm)
        result = await inferencer.infer(case_input, repo_profile)
        assert result.case_id == case_input.case_id

    async def test_enrich_profile_colors(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        assert enriched.design_tokens.colors["primary"] == "#3B82F6"
        assert enriched.design_tokens.colors["secondary"] == "#6B7280"

    async def test_enrich_profile_spacing(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        assert enriched.design_tokens.spacing["sm"] == "0.5rem"
        assert enriched.design_tokens.spacing["md"] == "1rem"

    async def test_enrich_profile_typography(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        assert "heading1" in enriched.design_tokens.typography

    async def test_enrich_profile_border_radius(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        assert enriched.design_tokens.border_radius["rounded"] == "0.25rem"

    async def test_enrich_profile_breakpoints(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        assert enriched.design_tokens.breakpoints["lg"] == "1024px"

    async def test_model_is_sonnet(
        self,
        case_input: CaseInput,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"analyze": mock_design_system_json})
        inferencer = DesignSystemInferencer(llm=fake_llm)
        await inferencer.infer(case_input, repo_profile)
        assert fake_llm.call_log[0]["config"].model == "claude-3-5-sonnet-20241022"

    async def test_system_prompt_key_is_analyze(self) -> None:
        first_word = _SYSTEM_PROMPT.split()[0].lower()
        assert first_word == "analyze"

    async def test_system_prompt_key_not_you(self) -> None:
        """Confirm no FakeLLMAdapter key collision with SemanticIntentExtractor."""
        first_word = _SYSTEM_PROMPT.split()[0].lower()
        assert first_word != "you"

    async def test_enrich_profile_does_not_mutate_original(
        self,
        repo_profile: RepoProfile,
        mock_design_system_json: str,
    ) -> None:
        ds = DesignSystem.model_validate(
            json.loads(mock_design_system_json) | {"case_id": "C-001"}
        )
        inferencer = DesignSystemInferencer(llm=FakeLLMAdapter())
        enriched = inferencer.enrich_profile(ds, repo_profile)
        # Original profile should not be mutated
        assert repo_profile.design_tokens.colors == {}
        # Enriched profile has colors
        assert len(enriched.design_tokens.colors) > 0


class TestDesignSystemNode:
    async def test_design_system_node_enriches_profile(
        self,
        case_input: CaseInput,
        mock_design_system_json: str,
    ) -> None:
        from unittest.mock import MagicMock

        from ddk.graph.nodes.design_system import design_system_node

        profile = RepoProfile(framework="react")
        fake_llm = FakeLLMAdapter(responses={"analyze": mock_design_system_json})
        container = MagicMock()
        container.llm = fake_llm

        state = {"case_input": case_input, "repo_profile": profile}
        result = await design_system_node(state, context=container)

        assert result["current_node"] == "design_system"
        assert result["repo_profile"].design_tokens.colors.get("primary") == "#3B82F6"

    async def test_design_system_node_no_llm_returns_error(
        self, case_input: CaseInput
    ) -> None:
        from ddk.graph.nodes.design_system import design_system_node

        profile = RepoProfile(framework="react")
        state = {"case_input": case_input, "repo_profile": profile}
        result = await design_system_node(state, context=None)

        assert result["terminal_state"] == "manual-review-required"
        assert "LLM" in result["error_message"]

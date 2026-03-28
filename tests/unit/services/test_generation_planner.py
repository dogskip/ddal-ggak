"""Unit tests for GenerationPlanner service (INGEST-06)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ddk.adapters.llm.base import LLMCallConfig
from ddk.models.generation import GenerationNode, GenerationPlan
from ddk.models.input import CaseInput
from ddk.models.intent import (
    BoundingBox,
    ComponentSpec,
    IntentGraph,
    InteractionSpec,
    LayoutRegion,
)
from ddk.models.repo import RepoProfile
from ddk.services.generation_planner import GenerationPlanner
from tests.fakes import FakeLLMAdapter


def _make_intent_graph() -> IntentGraph:
    return IntentGraph(
        id="case-001",
        source_image_hash="abc123",
        layout_regions=[
            LayoutRegion(
                id="region-header",
                region_type="header",
                bounds=BoundingBox(x=0.0, y=0.0, width=1.0, height=0.1),
                semantic_label="Header",
            )
        ],
        components=[
            ComponentSpec(
                id="comp-001",
                component_type="Button",
                region_id="region-header",
            )
        ],
        interactions=[],
        confidence=0.9,
    )


def _make_repo_profile() -> RepoProfile:
    return RepoProfile(framework="react")


def _make_plan_json(case_id: str = "case-001") -> dict[str, Any]:
    return {
        "case_id": case_id,
        "nodes": [
            {
                "id": "node-types",
                "node_type": "type",
                "target_path": "src/types/Header.ts",
                "dependencies": [],
                "validation_hooks": [],
                "repair_hooks": [],
            },
            {
                "id": "node-comp",
                "node_type": "component",
                "target_path": "src/components/Header.tsx",
                "dependencies": ["node-types"],
                "validation_hooks": ["typecheck"],
                "repair_hooks": [],
            },
        ],
        "execution_order": ["node-types", "node-comp"],
        "target_files": ["src/types/Header.ts", "src/components/Header.tsx"],
        "validation_hooks": ["typecheck"],
        "estimated_node_count": 2,
        "created_at": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    plan_json = _make_plan_json()
    return FakeLLMAdapter(responses={"senior": json.dumps(plan_json)})


@pytest.fixture
def planner(fake_llm: FakeLLMAdapter) -> GenerationPlanner:
    return GenerationPlanner(llm=fake_llm)


class TestGenerationPlanner:
    async def test_plan_returns_generation_plan(
        self, planner: GenerationPlanner
    ) -> None:
        """FakeLLM response is parsed into a GenerationPlan."""
        result = await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Create a header component",
        )
        assert isinstance(result, GenerationPlan)
        assert result.case_id == "case-001"
        assert len(result.nodes) == 2

    async def test_execution_order_set(self, planner: GenerationPlanner) -> None:
        """execution_order is populated with node IDs."""
        result = await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Create a header",
        )
        assert result.execution_order == ["node-types", "node-comp"]

    async def test_target_files_collected(self, planner: GenerationPlanner) -> None:
        """target_files are collected from nodes."""
        result = await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Create a header",
        )
        assert "src/types/Header.ts" in result.target_files
        assert "src/components/Header.tsx" in result.target_files

    async def test_estimated_node_count_matches(
        self, planner: GenerationPlanner
    ) -> None:
        """estimated_node_count matches len(nodes)."""
        result = await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Build me a header",
        )
        assert result.estimated_node_count == len(result.nodes)

    async def test_model_is_sonnet(self, fake_llm: FakeLLMAdapter) -> None:
        """GenerationPlanner uses claude-3-5-sonnet-20241022 model."""
        planner = GenerationPlanner(llm=fake_llm)
        await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Build me a header",
        )
        assert len(fake_llm.call_log) == 1
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.model == "claude-3-5-sonnet-20241022"

    async def test_temperature_zero(self, fake_llm: FakeLLMAdapter) -> None:
        """temperature=0 ensures determinism."""
        planner = GenerationPlanner(llm=fake_llm)
        await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Build me a header",
        )
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.temperature == 0.0

    async def test_deterministic_same_input(
        self, fake_llm: FakeLLMAdapter
    ) -> None:
        """Two calls with same input produce equivalent GenerationPlan."""
        planner = GenerationPlanner(llm=fake_llm)
        intent = _make_intent_graph()
        profile = _make_repo_profile()

        result1 = await planner.plan(
            case_id="case-001",
            intent_graph=intent,
            repo_profile=profile,
            user_prompt="Create header",
        )
        result2 = await planner.plan(
            case_id="case-001",
            intent_graph=intent,
            repo_profile=profile,
            user_prompt="Create header",
        )
        assert result1.case_id == result2.case_id
        assert [n.id for n in result1.nodes] == [n.id for n in result2.nodes]
        assert result1.execution_order == result2.execution_order

    async def test_node_types_correct(self, planner: GenerationPlanner) -> None:
        """Nodes have valid node_type values from the GenerationNode Literal."""
        result = await planner.plan(
            case_id="case-001",
            intent_graph=_make_intent_graph(),
            repo_profile=_make_repo_profile(),
            user_prompt="Build components",
        )
        valid_types = {"file", "component", "hook", "style", "test", "route", "type"}
        for node in result.nodes:
            assert node.node_type in valid_types


class TestPlanNode:
    async def test_plan_node_thin_adapter(
        self, fake_llm: FakeLLMAdapter, tmp_path: Path
    ) -> None:
        """plan_node reads intent_graph + repo_profile, calls planner, writes generation_plan."""
        from unittest.mock import AsyncMock, MagicMock

        from ddk.graph.nodes.plan import plan_node
        from ddk.graph.context import ServiceContainer

        # Build minimal state
        img = tmp_path / "design.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 20)
        case_input = CaseInput(
            case_id="case-001",
            image_paths=[img],
            prompt="Build header",
            repo_path=tmp_path,
        )
        state = {
            "case_id": "case-001",
            "case_input": case_input,
            "intent_graph": _make_intent_graph(),
            "repo_profile": _make_repo_profile(),
        }

        # Create container with fake llm
        container = MagicMock(spec=ServiceContainer)
        container.llm = fake_llm

        result = await plan_node(state, context=container)
        assert "generation_plan" in result
        assert result["current_node"] == "plan"
        assert isinstance(result["generation_plan"], GenerationPlan)

    async def test_plan_node_no_llm_returns_error(
        self, tmp_path: Path
    ) -> None:
        """plan_node with no LLM returns error state."""
        from unittest.mock import MagicMock

        from ddk.graph.nodes.plan import plan_node
        from ddk.graph.context import ServiceContainer

        img = tmp_path / "design.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 20)
        case_input = CaseInput(
            case_id="case-001",
            image_paths=[img],
            prompt="Build header",
            repo_path=tmp_path,
        )
        state = {
            "case_id": "case-001",
            "case_input": case_input,
            "intent_graph": _make_intent_graph(),
            "repo_profile": _make_repo_profile(),
        }

        container = MagicMock(spec=ServiceContainer)
        container.llm = None

        result = await plan_node(state, context=container)
        assert result.get("terminal_state") == "manual-review-required"

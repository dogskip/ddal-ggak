"""Unit tests for CodeGenerator service and generate_node adapter (CODEGEN-01)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from ddk.adapters.llm.base import LLMCallConfig
from ddk.models.generation import GeneratedArtifactSet, GenerationNode, GenerationPlan
from ddk.models.input import CaseInput
from ddk.models.intent import (
    BoundingBox,
    ComponentSpec,
    IntentGraph,
    LayoutRegion,
)
from ddk.models.repo import RepoProfile
from ddk.services.code_generator import CodeGenerator
from tests.fakes import FakeLLMAdapter

# ---------------------------------------------------------------------------
# Fake response data
# ---------------------------------------------------------------------------

_FAKE_NODE_RESPONSE = json.dumps(
    {
        "files": [
            {
                "path": "src/components/Button.tsx",
                "content": "export const Button = () => <button/>;",
                "language": "typescript",
                "source_node_id": "node-001",
                "is_new": True,
            }
        ],
        "entry_point": "src/components/Button.tsx",
        "component_exports": ["Button"],
    }
)

_FAKE_NODE_RESPONSE_TYPED = json.dumps(
    {
        "files": [
            {
                "path": "src/types/Button.ts",
                "content": "export interface ButtonProps { label: string; }",
                "language": "typescript",
                "source_node_id": "node-types",
                "is_new": True,
            }
        ],
        "entry_point": None,
        "component_exports": [],
    }
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


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


def _make_one_node_plan() -> GenerationPlan:
    return GenerationPlan(
        case_id="case-001",
        nodes=[
            GenerationNode(
                id="node-001",
                node_type="component",
                target_path="src/components/Button.tsx",
            )
        ],
        execution_order=["node-001"],
        target_files=["src/components/Button.tsx"],
        estimated_node_count=1,
    )


def _make_three_node_plan() -> GenerationPlan:
    return GenerationPlan(
        case_id="case-002",
        nodes=[
            GenerationNode(
                id="node-001",
                node_type="type",
                target_path="src/types/Button.ts",
            ),
            GenerationNode(
                id="node-002",
                node_type="component",
                target_path="src/components/Button.tsx",
            ),
            GenerationNode(
                id="node-003",
                node_type="test",
                target_path="src/components/Button.test.tsx",
            ),
        ],
        execution_order=["node-001", "node-002", "node-003"],
        target_files=[
            "src/types/Button.ts",
            "src/components/Button.tsx",
            "src/components/Button.test.tsx",
        ],
        estimated_node_count=3,
    )


def _make_empty_plan() -> GenerationPlan:
    return GenerationPlan(
        case_id="case-empty",
        nodes=[],
        execution_order=[],
        target_files=[],
        estimated_node_count=0,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    return FakeLLMAdapter(responses={"generate": _FAKE_NODE_RESPONSE})


@pytest.fixture
def generator(fake_llm: FakeLLMAdapter) -> CodeGenerator:
    return CodeGenerator(llm=fake_llm)


# ---------------------------------------------------------------------------
# TestCodeGenerator — 7 tests covering CodeGenerator.generate_all()
# ---------------------------------------------------------------------------


class TestCodeGenerator:
    async def test_generate_all_returns_artifact_set(
        self, generator: CodeGenerator
    ) -> None:
        """generate_all() returns GeneratedArtifactSet with correct case_id."""
        plan = _make_one_node_plan()
        result = await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create a Button component",
        )
        assert isinstance(result, GeneratedArtifactSet)
        assert result.case_id == "case-001"

    async def test_one_llm_call_per_node(
        self, fake_llm: FakeLLMAdapter
    ) -> None:
        """generate_all() with 3-node plan makes exactly 3 LLM calls (one per node)."""
        generator = CodeGenerator(llm=fake_llm)
        plan = _make_three_node_plan()
        await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create Button with types and tests",
        )
        assert len(fake_llm.call_log) == 3

    async def test_empty_plan_returns_empty_artifacts(
        self, fake_llm: FakeLLMAdapter
    ) -> None:
        """Empty execution_order → empty GeneratedArtifactSet, 0 LLM calls."""
        generator = CodeGenerator(llm=fake_llm)
        plan = _make_empty_plan()
        result = await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="nothing to do",
        )
        assert isinstance(result, GeneratedArtifactSet)
        assert result.files == []
        assert result.file_map == {}
        assert len(fake_llm.call_log) == 0

    async def test_file_map_contains_all_paths(
        self, generator: CodeGenerator
    ) -> None:
        """file_map keys match file paths from LLM response."""
        plan = _make_one_node_plan()
        result = await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create Button",
        )
        assert "src/components/Button.tsx" in result.file_map
        assert result.file_map["src/components/Button.tsx"] == (
            "export const Button = () => <button/>;"
        )

    async def test_generation_trace_has_one_entry_per_node(
        self, generator: CodeGenerator
    ) -> None:
        """generation_trace has one entry for each node processed."""
        plan = _make_one_node_plan()
        result = await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create Button",
        )
        assert len(result.generation_trace) == 1
        assert "node-001" in result.generation_trace[0]

    async def test_model_is_claude_sonnet(
        self, fake_llm: FakeLLMAdapter
    ) -> None:
        """CodeGenerator uses model=claude-3-5-sonnet-20241022."""
        generator = CodeGenerator(llm=fake_llm)
        plan = _make_one_node_plan()
        await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create Button",
        )
        assert len(fake_llm.call_log) == 1
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.model == "claude-3-5-sonnet-20241022"

    async def test_temperature_is_zero(
        self, fake_llm: FakeLLMAdapter
    ) -> None:
        """CodeGenerator uses temperature=0.0 for determinism."""
        generator = CodeGenerator(llm=fake_llm)
        plan = _make_one_node_plan()
        await generator.generate_all(
            plan=plan,
            repo_profile=_make_repo_profile(),
            intent_graph=_make_intent_graph(),
            prompt="Create Button",
        )
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.temperature == 0.0


# ---------------------------------------------------------------------------
# TestGenerateNode — 2 tests for generate_node thin adapter
# ---------------------------------------------------------------------------


class TestGenerateNode:
    async def test_generate_node_thin_adapter(
        self, fake_llm: FakeLLMAdapter, tmp_path: Path
    ) -> None:
        """generate_node reads state, calls CodeGenerator, writes generated_artifacts."""
        from ddk.graph.context import ServiceContainer
        from ddk.graph.nodes.generate import generate_node

        img = tmp_path / "design.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 20)
        case_input = CaseInput(
            case_id="case-001",
            image_paths=[img],
            prompt="Build Button component",
            repo_path=tmp_path,
        )

        state: dict[str, Any] = {
            "case_id": "case-001",
            "case_input": case_input,
            "generation_plan": _make_one_node_plan(),
            "repo_profile": _make_repo_profile(),
            "intent_graph": _make_intent_graph(),
        }

        container = MagicMock(spec=ServiceContainer)
        container.llm = fake_llm

        result = await generate_node(state, context=container)
        assert "generated_artifacts" in result
        assert result["current_node"] == "generate"
        assert isinstance(result["generated_artifacts"], GeneratedArtifactSet)

    async def test_generate_node_no_llm_returns_error(
        self, tmp_path: Path
    ) -> None:
        """generate_node with no LLM returns terminal_state=manual-review-required."""
        from ddk.graph.context import ServiceContainer
        from ddk.graph.nodes.generate import generate_node

        img = tmp_path / "design.png"
        img.write_bytes(b"\x89PNG" + b"\x00" * 20)
        case_input = CaseInput(
            case_id="case-001",
            image_paths=[img],
            prompt="Build Button component",
            repo_path=tmp_path,
        )

        state: dict[str, Any] = {
            "case_id": "case-001",
            "case_input": case_input,
            "generation_plan": _make_one_node_plan(),
            "repo_profile": _make_repo_profile(),
            "intent_graph": _make_intent_graph(),
        }

        container = MagicMock(spec=ServiceContainer)
        container.llm = None

        result = await generate_node(state, context=container)
        assert result.get("terminal_state") == "manual-review-required"

"""The recorded model answers of the demo are valid input for each stage that reads them."""

from __future__ import annotations

import json
from pathlib import Path

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.demo.script import demo_model, recorded_session
from ddk.demo.wireframe import first_draft_boxes, page_source, reference_boxes
from ddk.models.design_system import DesignSystem
from ddk.models.generation import GenerationPlan
from ddk.models.input import CaseInput
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile
from ddk.services.design_system_inferencer import DesignSystemInferencer
from ddk.services.file_blocks import parse_file_blocks
from ddk.services.generation_planner import GenerationPlanner
from ddk.services.semantic_intent_extractor import SemanticIntentExtractor
from tests.fakes.images import write_png


def _answer(purpose: str) -> str:
    return next(call["content"] for call in recorded_session() if call["purpose"] == purpose)


def test_one_answer_per_stage_in_the_order_the_stages_ask() -> None:
    purposes = [call["purpose"] for call in recorded_session()]

    assert purposes == ["you", "analyze", "senior", "generate", "normalize", "autofix-visual"]


def test_first_attempt_is_the_draft_and_the_repair_is_the_design() -> None:
    assert parse_file_blocks(_answer("generate")) == [
        ("src/App.tsx", page_source(first_draft_boxes()))
    ]
    assert _answer("autofix-visual") == page_source(reference_boxes())


def test_normalizer_answer_changes_nothing() -> None:
    assert json.loads(_answer("normalize"))["patched_files"] == {}


async def test_stages_accept_their_recorded_answers(tmp_path: Path) -> None:
    case = CaseInput(
        case_id="C-001",
        image_paths=[write_png(tmp_path / "design.png")],
        prompt="Build the dashboard",
        repo_path=tmp_path,
    )
    llm = demo_model()

    intent = await SemanticIntentExtractor(llm).extract(case)
    design_system = await DesignSystemInferencer(llm).infer(case, RepoProfile(framework="react"))
    plan = await GenerationPlanner(llm).plan("C-001", intent, RepoProfile(framework="react"), "x")

    assert isinstance(intent, IntentGraph) and intent.layout_regions and intent.components
    assert isinstance(design_system, DesignSystem) and design_system.inferred_tokens
    assert isinstance(plan, GenerationPlan) and plan.target_files == ["src/App.tsx"]


async def test_replay_serves_each_answer_once_by_purpose() -> None:
    llm = demo_model()
    config = LLMCallConfig(metadata={"purpose": "generate"})

    first = await llm.complete([Message(role="system", content="Generate x")], config)

    assert first.content == _answer("generate")
    assert first.cost_usd == 0.0

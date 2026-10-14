"""generate_node gives the model the design image and the repository, and fails loudly."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.exceptions import GenerationError
from ddk.graph.nodes.generate import generate_node
from ddk.models.generation import GenerationNode, GenerationPlan
from ddk.models.input import CaseInput
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile


class SpyLLM:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls: list[list[Message]] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self.calls.append(messages)
        return LLMResponse(content=self.answer, model=config.model)

    async def complete_structured(
        self, messages: list[Message], config: LLMCallConfig, output_schema: type
    ) -> LLMResponse:
        return await self.complete(messages, config)


def _state(tmp_path: Path, image: Path) -> dict[str, Any]:
    return {
        "generation_plan": GenerationPlan(
            case_id="C-001",
            nodes=[GenerationNode(id="n1", node_type="component", target_path="src/Card.tsx")],
            execution_order=["n1"],
            target_files=["src/Card.tsx"],
        ),
        "repo_profile": RepoProfile(framework="react"),
        "intent_graph": IntentGraph(
            id="C-001",
            source_image_hash="h",
            layout_regions=[],
            components=[],
            interactions=[],
            confidence=0.9,
        ),
        "case_input": CaseInput(
            case_id="C-001", image_paths=[image], prompt="a card", repo_path=tmp_path
        ),
    }


@pytest.fixture
def design(tmp_path: Path) -> Path:
    path = tmp_path / "design.png"
    Image.new("RGB", (64, 48), (250, 250, 250)).save(path)
    return path


async def test_design_image_and_repo_files_reach_the_model(tmp_path: Path, design: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("export default function App() { return null }\n")
    llm = SpyLLM("=== FILE: src/Card.tsx ===\nexport const Card = () => null;\n")
    container = SimpleNamespace(llm=llm, primary_model="m", context_pack_builder=None)

    result = await generate_node(_state(tmp_path, design), context=container)

    user = llm.calls[0][-1]
    assert user.images is not None and user.images[0][1] == "image/png"
    assert "src/App.tsx" in user.content
    artifacts = result["generated_artifacts"]
    assert [(f.path, f.is_new) for f in artifacts.files] == [("src/Card.tsx", True)]
    assert artifacts.trace["images"] == 1
    assert artifacts.trace["context_pack_hash"]


async def test_existing_target_file_keeps_its_original_content(
    tmp_path: Path, design: Path
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Card.tsx").write_text("old\n")
    llm = SpyLLM("=== FILE: src/Card.tsx ===\nnew\n")
    container = SimpleNamespace(llm=llm, primary_model="m", context_pack_builder=None)

    result = await generate_node(_state(tmp_path, design), context=container)

    (generated,) = result["generated_artifacts"].files
    assert (generated.is_new, generated.original_content) == (False, "old\n")


async def test_design_image_pillow_cannot_decode_is_still_sent(tmp_path: Path) -> None:
    raw = b"not an image"
    odd = tmp_path / "design.png"
    odd.write_bytes(raw)
    llm = SpyLLM("=== FILE: src/Card.tsx ===\nexport const Card = () => null;\n")
    container = SimpleNamespace(llm=llm, primary_model="m", context_pack_builder=None)

    await generate_node(_state(tmp_path, odd), context=container)

    images = llm.calls[0][-1].images
    assert images == [(base64.b64encode(raw).decode("ascii"), "image/png")]


async def test_answer_without_a_file_is_an_error(tmp_path: Path, design: Path) -> None:
    container = SimpleNamespace(
        llm=SpyLLM("sorry, no code"), primary_model="m", context_pack_builder=None
    )

    with pytest.raises(GenerationError, match="n1"):
        await generate_node(_state(tmp_path, design), context=container)

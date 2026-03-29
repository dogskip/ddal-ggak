"""Unit tests for SemanticIntentExtractor (INGEST-04)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from ddk.models.input import CaseInput
from ddk.models.intent import IntentGraph
from ddk.services.semantic_intent_extractor import _SYSTEM_PROMPT, SemanticIntentExtractor
from tests.fakes.fake_llm_adapter import FakeLLMAdapter


@pytest.fixture
def mock_intent_graph_json() -> str:
    return json.dumps(
        {
            "id": "will-be-overwritten",
            "schema_version": "1.0",
            "source_image_hash": "will-be-overwritten",
            "layout_regions": [
                {
                    "id": "region-header",
                    "region_type": "header",
                    "bounds": {"x": 0.0, "y": 0.0, "width": 1.0, "height": 0.1},
                    "children": [],
                    "semantic_label": "Header",
                }
            ],
            "components": [
                {
                    "id": "comp-001",
                    "component_type": "Button",
                    "props": {"label": {"value": "로그인", "is_dynamic": False}},
                    "children": [],
                    "region_id": "region-header",
                    "confidence": 0.95,
                }
            ],
            "interactions": [
                {
                    "id": "int-001",
                    "trigger": "click",
                    "source_component_id": "comp-001",
                    "action": "navigate",
                    "target": "/login",
                }
            ],
            "confidence": 0.9,
            "unresolved_items": [],
        }
    )


@pytest.fixture
def case_input(tmp_path: Path) -> CaseInput:
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG" + b"\x00" * 50)
    return CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="로그인 페이지 UI 구현",
        repo_path=tmp_path,
    )


class TestSemanticIntentExtractor:
    async def test_extract_returns_intent_graph(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        result = await extractor.extract(case_input)
        assert isinstance(result, IntentGraph)
        assert result.id == "C-001"
        assert len(result.layout_regions) == 1
        assert len(result.components) == 1

    async def test_source_image_hash_computed(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        result = await extractor.extract(case_input)
        expected_hash = hashlib.sha256(
            case_input.image_paths[0].read_bytes()
        ).hexdigest()[:16]
        assert result.source_image_hash == expected_hash

    async def test_image_sent_as_base64(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        await extractor.extract(case_input)
        call = fake_llm.call_log[0]
        user_msg = next(m for m in call["messages"] if m.role == "user")
        assert user_msg.images is not None
        assert len(user_msg.images) == 1
        b64_data, media_type = user_msg.images[0]
        # Verify it's valid base64 and decodes to original bytes
        decoded = base64.standard_b64decode(b64_data)
        assert decoded == case_input.image_paths[0].read_bytes()
        assert media_type == "image/png"

    async def test_system_prompt_starts_with_you(self) -> None:
        first_word = _SYSTEM_PROMPT.split()[0].lower()
        assert first_word == "you"

    async def test_model_is_sonnet(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        await extractor.extract(case_input)
        assert fake_llm.call_log[0]["config"].model == "claude-3-5-sonnet-20241022"

    async def test_confidence_in_result(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        result = await extractor.extract(case_input)
        assert result.confidence == 0.9

    async def test_case_id_injected_as_graph_id(
        self, case_input: CaseInput, mock_intent_graph_json: str
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        extractor = SemanticIntentExtractor(llm=fake_llm)
        result = await extractor.extract(case_input)
        assert result.id == case_input.case_id


class TestIntentExtractNode:
    async def test_intent_extract_node_thin_adapter(
        self, case_input: CaseInput, mock_intent_graph_json: str, tmp_path: Path
    ) -> None:
        from unittest.mock import MagicMock

        from ddk.graph.nodes.intent_extract import intent_extract_node

        fake_llm = FakeLLMAdapter(responses={"you": mock_intent_graph_json})
        container = MagicMock()
        container.llm = fake_llm

        state = {"case_input": case_input}
        result = await intent_extract_node(state, context=container)

        assert result["current_node"] == "intent_extract"
        assert isinstance(result["intent_graph"], IntentGraph)
        assert result["intent_graph"].id == "C-001"

    async def test_intent_extract_node_no_llm_returns_error(
        self, case_input: CaseInput
    ) -> None:
        from ddk.graph.nodes.intent_extract import intent_extract_node

        state = {"case_input": case_input}
        result = await intent_extract_node(state, context=None)

        assert result["terminal_state"] == "manual-review-required"
        assert "LLM" in result["error_message"]

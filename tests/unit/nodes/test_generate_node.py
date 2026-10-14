"""Tests for generate_node — graph/nodes/generate.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.graph.nodes.generate import generate_node


def _make_state(**overrides: Any) -> dict[str, Any]:
    """Build a minimal graph state for the generate node."""
    base: dict[str, Any] = {
        "generation_plan": MagicMock(),
        "repo_profile": MagicMock(),
        "intent_graph": MagicMock(),
        "case_input": MagicMock(),
    }
    base.update(overrides)
    return base


def _mock_container() -> MagicMock:
    """Build a mock ServiceContainer with a fake LLM."""
    container = MagicMock()
    container.llm = MagicMock()
    return container


class TestGenerateNodeMissing:
    """When required upstream state fields are missing."""

    @pytest.mark.asyncio
    async def test_missing_generation_plan(self) -> None:
        state = _make_state(generation_plan=None)
        result = await generate_node(state, context=_mock_container())
        assert result["terminal_state"] == "manual-review-required"
        assert "generation_plan" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_repo_profile(self) -> None:
        state = _make_state(repo_profile=None)
        result = await generate_node(state, context=_mock_container())
        assert result["terminal_state"] == "manual-review-required"
        assert "repo_profile" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_intent_graph(self) -> None:
        state = _make_state(intent_graph=None)
        result = await generate_node(state, context=_mock_container())
        assert result["terminal_state"] == "manual-review-required"
        assert "intent_graph" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_case_input(self) -> None:
        state = _make_state(case_input=None)
        result = await generate_node(state, context=_mock_container())
        assert result["terminal_state"] == "manual-review-required"
        assert "case_input" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_multiple(self) -> None:
        state = _make_state(generation_plan=None, case_input=None)
        result = await generate_node(state, context=_mock_container())
        assert result["terminal_state"] == "manual-review-required"
        assert "generation_plan" in result["error_message"]
        assert "case_input" in result["error_message"]

    @pytest.mark.asyncio
    async def test_no_container_returns_error(self) -> None:
        state = _make_state()
        result = await generate_node(state)
        assert result["terminal_state"] == "manual-review-required"
        assert "LLM" in result["error_message"]


class TestGenerateNodeAssertRemoved:
    """Verify assert statements were replaced with RuntimeError."""

    @pytest.mark.asyncio
    async def test_no_assert_in_source(self) -> None:
        """Source code must not contain bare assert for safety under -O."""
        import inspect

        source = inspect.getsource(generate_node)
        assert "assert " not in source, (
            "generate_node still contains `assert` statements; "
            "they must be `if not X: raise RuntimeError(...)` for -O safety"
        )


class TestGenerateNodeSuccess:
    """Happy path when all state fields are present."""

    @pytest.mark.asyncio
    async def test_delegates_to_code_generator(self) -> None:
        mock_container = MagicMock()
        mock_generator = MagicMock()
        fake_artifacts = [MagicMock()]
        mock_generator.generate_all = AsyncMock(return_value=fake_artifacts)

        state = _make_state()
        with patch(
            "ddk.graph.nodes.generate.CodeGenerator",
            return_value=mock_generator,
        ):
            result = await generate_node(state, context=mock_container)

        assert result["generated_artifacts"] == fake_artifacts
        assert result["current_node"] == "generate"
        mock_generator.generate_all.assert_awaited_once()

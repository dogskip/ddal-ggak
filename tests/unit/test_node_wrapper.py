"""Regression tests for LangGraph context injection in node_wrapper."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TypedDict

import pytest
from langgraph.graph import START, StateGraph

from ddk.graph.nodes._wrapper import _extract_context, node_wrapper


class _State(TypedDict):
    current_node: str
    saw_context: bool


@dataclass
class _Context:
    flag: str


async def _context_echo_node(state: dict[str, object], **kwargs: object) -> dict[str, object]:
    context = kwargs.get("context")
    return {
        "current_node": "echo",
        "saw_context": isinstance(context, _Context) and context.flag == "ok",
    }


@pytest.mark.asyncio
async def test_extract_context_supports_pregel_runtime_key() -> None:
    marker = object()
    config = {
        "configurable": {
            "__pregel_runtime": SimpleNamespace(context=marker),
        }
    }

    assert _extract_context(config) is marker


@pytest.mark.asyncio
async def test_node_wrapper_injects_context_in_compiled_graph() -> None:
    workflow: StateGraph = StateGraph(_State, context_schema=_Context)  # type: ignore[type-arg]
    workflow.add_node("echo", node_wrapper(_context_echo_node))  # type: ignore[arg-type]
    workflow.add_edge(START, "echo")

    graph = workflow.compile()
    result = await graph.ainvoke(
        {"current_node": "start", "saw_context": False},
        context=_Context(flag="ok"),
    )

    assert result["saw_context"] is True
    assert result["current_node"] == "echo"

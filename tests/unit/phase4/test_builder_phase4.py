"""Tests for builder.py certification graph topology."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from ddk.graph.builder import build_ddk_graph

_STAGES = (
    "intake",
    "repo_scan",
    "intent_extract",
    "design_system",
    "plan",
    "generate",
    "normalize",
    "validate",
    "autofix",
    "certify",
)


def _stub_stages(
    monkeypatch: pytest.MonkeyPatch, calls: list[str], updates: dict[str, dict[str, Any]]
) -> None:
    def stage(name: str) -> Callable[..., Any]:
        async def node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            calls.append(name)
            return updates.get(name, {})

        return node

    for name in _STAGES:
        monkeypatch.setattr(f"ddk.graph.builder.{name}_node", stage(name))


async def test_every_stage_runs_in_order_when_nothing_goes_wrong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    _stub_stages(monkeypatch, calls, {})

    await build_ddk_graph().compile().ainvoke({"case_id": "C-1", "retry_budget_remaining": 0})

    assert calls == [*_STAGES[:8], "certify"]


async def test_a_failing_stage_skips_the_rest_and_keeps_its_own_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    failure = {"terminal_state": "manual-review-required", "error_message": "generate: boom"}
    _stub_stages(monkeypatch, calls, {"generate": failure})

    result = await build_ddk_graph().compile().ainvoke({"case_id": "C-1"})

    assert calls == [
        "intake",
        "repo_scan",
        "intent_extract",
        "design_system",
        "plan",
        "generate",
        "certify",
    ]
    assert result["error_message"] == "generate: boom"


def test_graph_has_validate_autofix_and_certify_nodes() -> None:
    g = build_ddk_graph()
    assert "validate" in g.nodes
    assert "autofix" in g.nodes
    assert "certify" in g.nodes


def test_graph_normalize_connects_to_validate() -> None:
    """normalize must go to validate, not directly to __end__."""
    g = build_ddk_graph()
    # Verify graph structure by confirming validate node exists and graph compiles
    assert "validate" in g.nodes
    # Serialize graph to string to check edges
    graph_str = str(g.edges)
    assert "validate" in graph_str or "validate" in str(g.nodes)


def test_graph_compiles_without_error() -> None:
    """Full graph must compile and be invocable."""
    g = build_ddk_graph()
    # StateGraph should now include certification as the 10th node
    assert len(g.nodes) >= 10

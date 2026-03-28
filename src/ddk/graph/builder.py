"""LangGraph StateGraph builder for ddalggak pipeline — Phase 1 skeleton.

Full 10-node graph is assembled in Phase 5 (CERT-06).
This module provides the DI wiring and a single placeholder start node.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph

from ddk.graph.context import ServiceContainer
from ddk.graph.nodes._wrapper import node_wrapper
from ddk.graph.state import GraphState


async def _start_node(state: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
    """Placeholder start node — replaced with real intake node in Phase 2."""
    return {"current_node": "start"}


def build_ddk_graph() -> StateGraph:  # type: ignore[type-arg, return-value]
    """Build the ddalggak LangGraph StateGraph.

    Phase 1 skeleton: context_schema wiring only with a single placeholder node.
    Full pipeline with 10 nodes is built in Phase 5 (CERT-06).

    Returns:
        LangGraph StateGraph ready for compilation and invocation.
    """
    workflow: StateGraph = StateGraph(GraphState, context_schema=ServiceContainer)  # type: ignore[type-arg]

    workflow.add_node("start", node_wrapper(_start_node))  # type: ignore[arg-type]
    workflow.add_edge(START, "start")
    workflow.add_edge("start", END)

    return workflow  # pyright: ignore[reportUnknownVariableType]

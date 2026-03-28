"""LangGraph StateGraph builder for ddalggak pipeline — Phase 2 partial graph (D-08).

5-node ingestion pipeline assembled here. Full 10-node graph is completed in Phase 5 (CERT-06).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ddk.graph.context import ServiceContainer
from ddk.graph.nodes._wrapper import node_wrapper
from ddk.graph.nodes.design_system import design_system_node
from ddk.graph.nodes.intake import intake_node
from ddk.graph.nodes.intent_extract import intent_extract_node
from ddk.graph.nodes.plan import plan_node
from ddk.graph.nodes.repo_scan import repo_scan_node
from ddk.graph.state import GraphState


def build_ddk_graph() -> StateGraph:  # type: ignore[type-arg, return-value]
    """Build the ddalggak LangGraph StateGraph.

    Phase 2 partial graph (D-08): 5-node ingestion pipeline.
    Flow: START → intake → repo_scan → intent_extract → design_system → plan → END

    Full 10-node pipeline is assembled in Phase 5 (CERT-06).

    Returns:
        LangGraph StateGraph ready for compilation and invocation.
    """
    workflow: StateGraph = StateGraph(GraphState, context_schema=ServiceContainer)  # type: ignore[type-arg]

    workflow.add_node("intake", node_wrapper(intake_node))  # type: ignore[arg-type]
    workflow.add_node("repo_scan", node_wrapper(repo_scan_node))  # type: ignore[arg-type]
    workflow.add_node("intent_extract", node_wrapper(intent_extract_node))  # type: ignore[arg-type]
    workflow.add_node("design_system", node_wrapper(design_system_node))  # type: ignore[arg-type]
    workflow.add_node("plan", node_wrapper(plan_node))  # type: ignore[arg-type]

    workflow.add_edge(START, "intake")
    workflow.add_edge("intake", "repo_scan")
    workflow.add_edge("repo_scan", "intent_extract")
    workflow.add_edge("intent_extract", "design_system")
    workflow.add_edge("design_system", "plan")
    workflow.add_edge("plan", END)

    return workflow  # pyright: ignore[reportUnknownVariableType]

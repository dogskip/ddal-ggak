"""LangGraph StateGraph builder for ddalggak pipeline — Phase 5.

10-node pipeline: START → intake → repo_scan → intent_extract → design_system → plan
                 → generate → normalize → validate → [route_after_validate]
                 (a stage that needs a human jumps to certify; the rest is skipped)
                 → {pass→certify, exhausted→certify, fix_available→autofix} ↩ validate
                 (autofix → certify when the patch changed nothing)
                 → certify → END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ddk.graph.context import ServiceContainer
from ddk.graph.nodes._wrapper import node_wrapper
from ddk.graph.nodes.autofix import autofix_node
from ddk.graph.nodes.certify import certify_node
from ddk.graph.nodes.design_system import design_system_node
from ddk.graph.nodes.generate import generate_node
from ddk.graph.nodes.intake import intake_node
from ddk.graph.nodes.intent_extract import intent_extract_node
from ddk.graph.nodes.normalize import normalize_node
from ddk.graph.nodes.plan import plan_node
from ddk.graph.nodes.repo_scan import repo_scan_node
from ddk.graph.nodes.validate import validate_node
from ddk.graph.router import route_after_autofix, route_after_stage, route_after_validate
from ddk.graph.state import GraphState


def build_ddk_graph() -> StateGraph:  # type: ignore[type-arg, return-value]
    """Build the ddalggak LangGraph StateGraph.

    Phase 5 (CERT-01/02/03/06/07): 10-node pipeline.
    Flow: START → intake → … → normalize → validate → [router]
          → {pass|exhausted → certify, fix_available → autofix → validate (back-edge)}
          → certify → END

    Returns:
        LangGraph StateGraph ready for compilation and invocation.
    """
    workflow: StateGraph = StateGraph(GraphState, context_schema=ServiceContainer)  # type: ignore[type-arg]

    # Linear generation pipeline (unchanged from Phase 3)
    workflow.add_node("intake", node_wrapper(intake_node))  # type: ignore[arg-type]
    workflow.add_node("repo_scan", node_wrapper(repo_scan_node))  # type: ignore[arg-type]
    workflow.add_node("intent_extract", node_wrapper(intent_extract_node))  # type: ignore[arg-type]
    workflow.add_node("design_system", node_wrapper(design_system_node))  # type: ignore[arg-type]
    workflow.add_node("plan", node_wrapper(plan_node))  # type: ignore[arg-type]
    workflow.add_node("generate", node_wrapper(generate_node))  # type: ignore[arg-type]
    workflow.add_node("normalize", node_wrapper(normalize_node))  # type: ignore[arg-type]

    # Phase 4 validation/self-healing nodes
    workflow.add_node("validate", node_wrapper(validate_node))  # type: ignore[arg-type]
    workflow.add_node("autofix", node_wrapper(autofix_node))  # type: ignore[arg-type]
    workflow.add_node("certify", node_wrapper(certify_node))  # type: ignore[arg-type]

    # Linear pipeline edges; a stage that needs a human skips the rest and keeps its own message
    workflow.add_edge(START, "intake")
    for current, following in (
        ("intake", "repo_scan"),
        ("repo_scan", "intent_extract"),
        ("intent_extract", "design_system"),
        ("design_system", "plan"),
        ("plan", "generate"),
        ("generate", "normalize"),
        ("normalize", "validate"),
    ):
        workflow.add_conditional_edges(
            current, route_after_stage, {"continue": following, "certify": "certify"}
        )

    # Conditional edge: validate → router → {pass|exhausted→certify, fix_available→autofix}
    workflow.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "pass": "certify",
            "exhausted": "certify",
            "fix_available": "autofix",
        },
    )

    # autofix back-edge → validate (self-healing loop), unless nothing could be patched
    workflow.add_conditional_edges(
        "autofix",
        route_after_autofix,
        {"validate": "validate", "certify": "certify"},
    )
    workflow.add_edge("certify", END)

    return workflow  # pyright: ignore[reportUnknownVariableType]

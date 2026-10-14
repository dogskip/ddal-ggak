"""The recorded model session of the demo: what each stage "answers", with no API call."""

from __future__ import annotations

import json
from typing import Any

from ddk.adapters.llm.recording import ReplayLLMAdapter
from ddk.demo.wireframe import first_draft_boxes, page_source, reference_boxes
from ddk.models.design_system import DesignSystem, InferredDesignToken
from ddk.models.generation import GenerationNode, GenerationPlan
from ddk.models.intent import BoundingBox, ComponentSpec, IntentGraph, LayoutRegion, PropValue

_MODEL = "recorded-demo"
_APP_PATH = "src/App.tsx"


def demo_model() -> ReplayLLMAdapter:
    """A model that replays the demo session."""
    return ReplayLLMAdapter(recorded_session())


def recorded_session() -> list[dict[str, Any]]:
    """One answer per stage, keyed by the purpose the stage asks with."""
    answers = {
        "you": _intent(),
        "analyze": _design_system(),
        "senior": _plan(),
        "generate": f"=== FILE: {_APP_PATH} ===\n{page_source(first_draft_boxes())}",
        "normalize": json.dumps(
            {"convention_fixes": [], "unresolved_drift": [], "patched_files": {}}
        ),
        "autofix-visual": page_source(reference_boxes()),
    }
    return [
        {"purpose": purpose, "model": _MODEL, "content": content}
        for purpose, content in answers.items()
    ]


def _intent() -> str:
    regions = [
        LayoutRegion(
            id="region-header",
            region_type="header",
            bounds=BoundingBox(x=0.0, y=0.0, width=1.0, height=0.09),
            semantic_label="top bar",
        ),
        *(
            LayoutRegion(
                id=f"region-card-{n}",
                region_type="card",
                bounds=BoundingBox(x=x, y=0.13, width=0.3, height=0.25),
                semantic_label="metric",
            )
            for n, x in enumerate((0.025, 0.35, 0.675), start=1)
        ),
        LayoutRegion(
            id="region-chart",
            region_type="main",
            bounds=BoundingBox(x=0.025, y=0.42, width=0.95, height=0.54),
            semantic_label="bar chart",
        ),
    ]
    components = [
        ComponentSpec(id="comp-header", component_type="Header", region_id="region-header"),
        *(
            ComponentSpec(
                id=f"comp-card-{n}",
                component_type="MetricCard",
                region_id=f"region-card-{n}",
                props={"accent": PropValue(value=accent)},
            )
            for n, accent in enumerate(("blue", "green", "red"), start=1)
        ),
        ComponentSpec(id="comp-chart", component_type="BarChart", region_id="region-chart"),
    ]
    graph = IntentGraph(
        id="",
        source_image_hash="",
        layout_regions=regions,
        components=components,
        interactions=[],
        confidence=0.9,
    )
    return graph.model_dump_json(exclude={"id", "source_image_hash", "created_at"})


def _design_system() -> str:
    tokens = [
        InferredDesignToken(name="navy", value="#0f172a", category="color", confidence=0.95),
        InferredDesignToken(name="surface", value="#f1f5f9", category="color", confidence=0.95),
        InferredDesignToken(name="blue", value="#2563eb", category="color", confidence=0.9),
        InferredDesignToken(name="green", value="#16a34a", category="color", confidence=0.9),
        InferredDesignToken(name="red", value="#dc2626", category="color", confidence=0.9),
        InferredDesignToken(name="gap", value="32px", category="spacing", confidence=0.8),
    ]
    system = DesignSystem(case_id="", inferred_tokens=tokens, primitive_components=["Box"])
    return system.model_dump_json(exclude={"case_id"})


def _plan() -> str:
    plan = GenerationPlan(
        case_id="",
        nodes=[
            GenerationNode(
                id="node-app",
                node_type="component",
                target_path=_APP_PATH,
                generation_prompt_hint="Draw the dashboard wireframe",
            )
        ],
        execution_order=["node-app"],
        target_files=[_APP_PATH],
        estimated_node_count=1,
    )
    return plan.model_dump_json(exclude={"case_id", "created_at"})

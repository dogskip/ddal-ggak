"""Roundtrip serialization tests for IntentGraph model family."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ddk.models.intent import (
    BoundingBox,
    ComponentSpec,
    InteractionSpec,
    IntentGraph,
    LayoutRegion,
    PropValue,
)


# ── BoundingBox ────────────────────────────────────────────────────


def test_bounding_box_roundtrip():
    bb = BoundingBox(x=0.1, y=0.2, width=0.5, height=0.3)
    json_str = bb.model_dump_json()
    restored = BoundingBox.model_validate_json(json_str)
    assert restored == bb


def test_bounding_box_rejects_negative():
    with pytest.raises(ValidationError):
        BoundingBox(x=-0.1, y=0.0, width=0.5, height=0.5)


def test_bounding_box_rejects_over_one():
    with pytest.raises(ValidationError):
        BoundingBox(x=1.1, y=0.0, width=0.5, height=0.5)


def test_bounding_box_rejects_zero_width():
    with pytest.raises(ValidationError):
        BoundingBox(x=0.0, y=0.0, width=0.0, height=0.5)


def test_bounding_box_edge_values():
    bb = BoundingBox(x=0.0, y=0.0, width=1.0, height=1.0)
    assert bb.x == 0.0
    assert bb.width == 1.0


# ── LayoutRegion ───────────────────────────────────────────────────


def test_layout_region_roundtrip():
    bb = BoundingBox(x=0.0, y=0.0, width=1.0, height=0.1)
    region = LayoutRegion(
        id="region-header",
        region_type="header",
        bounds=bb,
        children=["region-nav"],
        semantic_label="사이트 헤더",
    )
    json_str = region.model_dump_json()
    restored = LayoutRegion.model_validate_json(json_str)
    assert restored == region


def test_layout_region_defaults():
    bb = BoundingBox(x=0.0, y=0.0, width=1.0, height=0.5)
    region = LayoutRegion(id="region-main", region_type="main", bounds=bb)
    assert region.children == []
    assert region.semantic_label is None


# ── PropValue ──────────────────────────────────────────────────────


def test_prop_value_roundtrip_str():
    pv = PropValue(value="hello", is_dynamic=False)
    json_str = pv.model_dump_json()
    restored = PropValue.model_validate_json(json_str)
    assert restored == pv


def test_prop_value_roundtrip_int():
    pv = PropValue(value=42, is_dynamic=True)
    json_str = pv.model_dump_json()
    restored = PropValue.model_validate_json(json_str)
    assert restored == pv


def test_prop_value_roundtrip_bool():
    pv = PropValue(value=True, is_dynamic=False)
    json_str = pv.model_dump_json()
    restored = PropValue.model_validate_json(json_str)
    assert restored == pv


def test_prop_value_roundtrip_none():
    pv = PropValue(value=None, is_dynamic=False)
    json_str = pv.model_dump_json()
    restored = PropValue.model_validate_json(json_str)
    assert restored == pv


# ── ComponentSpec ──────────────────────────────────────────────────


def test_component_spec_nested_roundtrip():
    child = ComponentSpec(
        id="comp-child",
        component_type="Text",
        props={"text": PropValue(value="Hello")},
        children=[],
    )
    parent = ComponentSpec(
        id="comp-parent",
        component_type="Card",
        props={"variant": PropValue(value="outlined", is_dynamic=False)},
        children=[child],
        region_id="region-main",
        confidence=0.95,
        notes="카드 컴포넌트",
    )
    json_str = parent.model_dump_json()
    restored = ComponentSpec.model_validate_json(json_str)
    assert restored == parent
    assert len(restored.children) == 1
    assert restored.children[0].id == "comp-child"


def test_component_spec_defaults():
    cs = ComponentSpec(id="comp-001", component_type="Button")
    assert cs.props == {}
    assert cs.children == []
    assert cs.region_id is None
    assert cs.confidence == 1.0
    assert cs.notes is None


# ── InteractionSpec ────────────────────────────────────────────────


def test_interaction_spec_roundtrip():
    ispec = InteractionSpec(
        id="int-001",
        trigger="click",
        source_component_id="comp-001",
        action="navigate",
        target="/dashboard",
        params={"animate": True},
    )
    json_str = ispec.model_dump_json()
    restored = InteractionSpec.model_validate_json(json_str)
    assert restored == ispec


def test_interaction_spec_defaults():
    ispec = InteractionSpec(
        id="int-002",
        trigger="submit",
        source_component_id="comp-form",
        action="submit-form",
    )
    assert ispec.target is None
    assert ispec.params == {}


# ── IntentGraph ────────────────────────────────────────────────────


def _make_intent_graph(**overrides) -> IntentGraph:
    bb = BoundingBox(x=0.0, y=0.0, width=1.0, height=0.2)
    defaults = {
        "id": "C-001",
        "schema_version": "1.0",
        "source_image_hash": "abc123def4567890",
        "layout_regions": [
            LayoutRegion(id="r-header", region_type="header", bounds=bb),
        ],
        "components": [
            ComponentSpec(id="comp-001", component_type="Button"),
        ],
        "interactions": [
            InteractionSpec(
                id="int-001",
                trigger="click",
                source_component_id="comp-001",
                action="navigate",
            ),
        ],
        "confidence": 0.85,
        "unresolved_items": ["unclear icon"],
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return IntentGraph(**defaults)


def test_intent_graph_roundtrip():
    original = _make_intent_graph()
    json_str = original.model_dump_json()
    restored = IntentGraph.model_validate_json(json_str)
    assert restored == original


def test_intent_graph_empty_lists():
    ig = _make_intent_graph(
        layout_regions=[],
        components=[],
        interactions=[],
        unresolved_items=[],
    )
    json_str = ig.model_dump_json()
    restored = IntentGraph.model_validate_json(json_str)
    assert restored == ig
    assert restored.layout_regions == []
    assert restored.components == []
    assert restored.interactions == []


def test_intent_graph_defaults():
    ig = IntentGraph(
        id="C-002",
        source_image_hash="abcd1234abcd1234",
        layout_regions=[],
        components=[],
        interactions=[],
        confidence=0.5,
    )
    assert ig.schema_version == "1.0"
    assert ig.unresolved_items == []

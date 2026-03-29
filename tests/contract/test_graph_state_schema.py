"""Contract tests for GraphState schema — validates all 22 fields exist and have
correct types / defaults via initial_state factory."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.graph.state import GraphState, initial_state
from ddk.models.input import CaseInput


@pytest.fixture()
def sample_case_input(tmp_path: Path) -> CaseInput:
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG")
    return CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지 구현",
        repo_path=tmp_path,
    )


@pytest.fixture()
def state(sample_case_input: CaseInput) -> GraphState:
    return initial_state(sample_case_input)


class TestGraphStateFields:
    """All 22 TypedDict fields must be present."""

    EXPECTED_FIELDS = {
        "case_id",
        "case_input",
        "repo_profile",
        "intent_graph",
        "generation_plan",
        "generated_artifacts",
        "normalization_report",
        "runtime_validation_report",
        "visual_regression_report",
        "fix_attempts",
        "scorecard",
        "release_decision",
        "evidence_pack",
        "retry_budget_remaining",
        "current_node",
        "terminal_state",
        "error_message",
        "pre_run_checkpoint_ref",
        "failure_hash_history",
        "llm_call_records",
        "total_cost_usd",
        "reproducibility_seed",
    }

    def test_all_22_fields_present(self) -> None:
        hints = GraphState.__annotations__
        assert set(hints.keys()) == self.EXPECTED_FIELDS

    def test_field_count_is_22(self) -> None:
        assert len(GraphState.__annotations__) == 22


class TestInitialState:
    def test_case_id_propagated(self, state: GraphState, sample_case_input: CaseInput) -> None:
        assert state["case_id"] == sample_case_input.case_id

    def test_case_input_stored(self, state: GraphState, sample_case_input: CaseInput) -> None:
        assert state["case_input"] is sample_case_input

    def test_all_optional_fields_are_none(self, state: GraphState) -> None:
        none_fields = [
            "repo_profile",
            "intent_graph",
            "generation_plan",
            "generated_artifacts",
            "normalization_report",
            "runtime_validation_report",
            "visual_regression_report",
            "scorecard",
            "release_decision",
            "evidence_pack",
            "terminal_state",
            "error_message",
            "pre_run_checkpoint_ref",
            "reproducibility_seed",
        ]
        for field in none_fields:
            assert state[field] is None, f"Expected {field} to be None"

    def test_list_fields_are_empty(self, state: GraphState) -> None:
        assert state["fix_attempts"] == []
        assert state["failure_hash_history"] == []
        assert state["llm_call_records"] == []

    def test_retry_budget_default(self, state: GraphState) -> None:
        assert state["retry_budget_remaining"] == 3

    def test_current_node_default(self, state: GraphState) -> None:
        assert state["current_node"] == "start"

    def test_total_cost_default(self, state: GraphState) -> None:
        assert state["total_cost_usd"] == 0.0

    def test_all_fields_have_values(self, state: GraphState) -> None:
        """Every key in EXPECTED_FIELDS must be present in initial_state output."""
        for field in TestGraphStateFields.EXPECTED_FIELDS:
            assert field in state, f"Field {field!r} missing from initial_state()"

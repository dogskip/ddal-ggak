"""Contract test: list fields in GraphState must not share references.

LangGraph nodes should never mutate state in place. This test verifies that
initial_state() creates fresh list objects and that two separate calls do not
share the same list reference.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.graph.state import GraphState, initial_state
from ddk.models.input import CaseInput


@pytest.fixture()
def two_states(tmp_path: Path) -> tuple[GraphState, GraphState]:
    img = tmp_path / "d.png"
    img.write_bytes(b"\x89PNG")
    ci_a = CaseInput(case_id="C-001", image_paths=[img], prompt="A", repo_path=tmp_path)
    ci_b = CaseInput(case_id="C-002", image_paths=[img], prompt="B", repo_path=tmp_path)
    return initial_state(ci_a), initial_state(ci_b)


class TestListFieldImmutability:
    LIST_FIELDS = ("fix_attempts", "llm_call_records")

    def test_list_fields_not_shared_between_calls(
        self, two_states: tuple[GraphState, GraphState]
    ) -> None:
        state_a, state_b = two_states
        for field in self.LIST_FIELDS:
            assert state_a[field] is not state_b[field], (
                f"Field {field!r} shares the same list object between two initial_state() calls"
            )

    def test_mutating_one_does_not_affect_other(
        self, two_states: tuple[GraphState, GraphState]
    ) -> None:
        state_a, state_b = two_states
        state_a["fix_attempts"].append("sentinel")  # type: ignore[arg-type]
        assert state_b["fix_attempts"] == [], (
            "Mutating fix_attempts on state_a should not affect state_b"
        )

    def test_list_fields_are_new_instances_each_call(self, tmp_path: Path) -> None:
        img = tmp_path / "d.png"
        img.write_bytes(b"\x89PNG")
        ci = CaseInput(case_id="C-001", image_paths=[img], prompt="test", repo_path=tmp_path)
        s1 = initial_state(ci)
        s2 = initial_state(ci)
        for field in self.LIST_FIELDS:
            assert s1[field] is not s2[field]


class TestRetryBudget:
    def test_default_budget_is_three(self, tmp_path: Path) -> None:
        img = tmp_path / "d.png"
        img.write_bytes(b"\x89PNG")
        ci = CaseInput(case_id="C-001", image_paths=[img], prompt="t", repo_path=tmp_path)

        assert initial_state(ci)["retry_budget_remaining"] == 3

    def test_budget_is_configurable(self, tmp_path: Path) -> None:
        img = tmp_path / "d.png"
        img.write_bytes(b"\x89PNG")
        ci = CaseInput(case_id="C-001", image_paths=[img], prompt="t", repo_path=tmp_path)

        assert initial_state(ci, retry_budget=7)["retry_budget_remaining"] == 7

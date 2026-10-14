"""PipelineRunner reports every finished stage while the graph runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from ddk.models.input import CaseInput
from ddk.services.pipeline_runner import PipelineRunner, RuntimeServices
from tests.fakes.images import write_png

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


def _services() -> RuntimeServices:
    return RuntimeServices(
        llm=MagicMock(),
        filesystem=MagicMock(),
        git=MagicMock(),
        build_runner=MagicMock(),
        sandbox=MagicMock(),
        screenshot_diff=MagicMock(),
        browser=AsyncMock(),
        max_fix_attempts=0,
    )


def _stub_stages(monkeypatch: pytest.MonkeyPatch, updates: dict[str, dict[str, Any]]) -> None:
    def stage(name: str) -> Any:
        async def node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
            return {"current_node": name, **updates.get(name, {})}

        return node

    for name in _STAGES:
        monkeypatch.setattr(f"ddk.graph.builder.{name}_node", stage(name))


def _case(tmp_path: Path) -> CaseInput:
    return CaseInput(
        case_id="C-001",
        image_paths=[write_png(tmp_path / "design.png")],
        prompt="x",
        repo_path=tmp_path,
    )


async def test_every_stage_is_reported_with_what_it_returned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_stages(monkeypatch, {"generate": {"error_message": None, "total_cost_usd": 0.5}})
    seen: list[tuple[str, dict[str, Any]]] = []

    result = await PipelineRunner(_services()).run_case(
        _case(tmp_path), on_update=lambda node, update: seen.append((node, update))
    )

    assert [node for node, _ in seen] == [*_STAGES[:8], "certify"]
    assert dict(seen)["generate"]["total_cost_usd"] == 0.5
    assert result["current_node"] == "certify"
    assert result["total_cost_usd"] == 0.5
    assert result["llm_calls"] == []


async def test_without_a_callback_the_result_is_the_same(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_stages(monkeypatch, {})

    result = await PipelineRunner(_services()).run_case(_case(tmp_path))

    assert result["current_node"] == "certify"

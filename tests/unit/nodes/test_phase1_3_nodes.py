"""Unit tests for all Phase 1–3 graph nodes (D-05 thin adapters).

Each node follows the same pattern:
1. Read ServiceContainer from kwargs
2. Guard against missing container → manual-review-required
3. Guard against missing upstream state → manual-review-required
4. Call the corresponding service method
5. Return updated state dict with current_node set

Test strategy:
- Happy path: mock the service, verify state update
- Missing container: verify terminal_state="manual-review-required"
- Missing upstream state: verify terminal_state="manual-review-required"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.graph.nodes.design_system import design_system_node
from ddk.graph.nodes.generate import generate_node
from ddk.graph.nodes.intake import intake_node
from ddk.graph.nodes.intent_extract import intent_extract_node
from ddk.graph.nodes.normalize import normalize_node
from ddk.graph.nodes.plan import plan_node
from ddk.graph.nodes.repo_scan import repo_scan_node
from ddk.models.config import DEFAULT_LIGHT_MODEL

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_case_input() -> MagicMock:
    """Minimal CaseInput mock with required attributes."""
    ci = MagicMock()
    ci.case_id = "C-001"
    ci.prompt = "Build a login form"
    ci.repo_path = Path("/tmp/test-repo")
    ci.image_paths = [Path("/tmp/img.png")]
    return ci


def _make_intent_graph() -> MagicMock:
    fields = ["id", "schema_version", "source_image_hash", "layout_regions", "components"]
    return MagicMock(spec_set=fields)


def _make_repo_profile() -> MagicMock:
    return MagicMock(spec_set=["framework", "language", "package_manager", "css_approach"])


def _make_generation_plan() -> MagicMock:
    return MagicMock(spec_set=["case_id", "nodes", "execution_order", "target_files"])


def _make_artifacts() -> MagicMock:
    fields = ["case_id", "files", "file_map", "generation_trace", "total_tokens_used"]
    return MagicMock(spec_set=fields)


def _make_container(**overrides: Any) -> MagicMock:
    """Build a ServiceContainer mock with sensible defaults."""
    container = MagicMock()
    container.llm = overrides.get("llm", MagicMock())
    return container


# ===========================================================================
# intake_node
# ===========================================================================
class TestIntakeNode:
    """intake_node does NOT require a container — it directly instantiates IntakeProcessor."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        case_input = _make_case_input()
        validated = MagicMock()
        with patch("ddk.graph.nodes.intake.IntakeProcessor") as mock_processor:
            instance = mock_processor.return_value
            instance.process = AsyncMock(return_value=(validated, []))
            result = await intake_node({"case_input": case_input})

        assert result["current_node"] == "intake"
        assert result["case_input"] is validated

    @pytest.mark.asyncio
    async def test_propagates_service_error(self) -> None:
        """If IntakeProcessor raises, the error propagates (no swallowing)."""
        case_input = _make_case_input()
        with patch("ddk.graph.nodes.intake.IntakeProcessor") as mock_processor:
            instance = mock_processor.return_value
            instance.process = AsyncMock(side_effect=ValueError("bad input"))
            with pytest.raises(ValueError, match="bad input"):
                await intake_node({"case_input": case_input})


# ===========================================================================
# intent_extract_node
# ===========================================================================
class TestIntentExtractNode:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        case_input = _make_case_input()
        intent_graph = _make_intent_graph()
        container = _make_container()
        with patch("ddk.graph.nodes.intent_extract.SemanticIntentExtractor") as mock_extractor:
            instance = mock_extractor.return_value
            instance.extract = AsyncMock(return_value=intent_graph)
            result = await intent_extract_node(
                {"case_input": case_input},
                context=container,
            )

        assert result["current_node"] == "intent_extract"
        assert result["intent_graph"] is intent_graph

    @pytest.mark.asyncio
    async def test_missing_container(self) -> None:
        result = await intent_extract_node({"case_input": _make_case_input()})
        assert result["terminal_state"] == "manual-review-required"
        assert "No LLM" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_case_input(self) -> None:
        container = _make_container()
        result = await intent_extract_node({"case_input": None}, context=container)
        assert result["terminal_state"] == "manual-review-required"
        assert "case_input" in result["error_message"]


# ===========================================================================
# design_system_node
# ===========================================================================
class TestDesignSystemNode:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        case_input = _make_case_input()
        repo_profile = _make_repo_profile()
        design_system = MagicMock()
        enriched = MagicMock()
        container = _make_container()
        with patch("ddk.graph.nodes.design_system.DesignSystemInferencer") as mock_inf:
            instance = mock_inf.return_value
            instance.infer = AsyncMock(return_value=design_system)
            instance.enrich_profile = MagicMock(return_value=enriched)
            result = await design_system_node(
                {"case_input": case_input, "repo_profile": repo_profile},
                context=container,
            )

        assert result["current_node"] == "design_system"
        assert result["repo_profile"] is enriched

    @pytest.mark.asyncio
    async def test_missing_container(self) -> None:
        result = await design_system_node(
            {"case_input": _make_case_input(), "repo_profile": _make_repo_profile()},
        )
        assert result["terminal_state"] == "manual-review-required"

    @pytest.mark.asyncio
    async def test_missing_case_input(self) -> None:
        container = _make_container()
        result = await design_system_node(
            {"case_input": None, "repo_profile": _make_repo_profile()},
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "case_input" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_repo_profile(self) -> None:
        container = _make_container()
        result = await design_system_node(
            {"case_input": _make_case_input(), "repo_profile": None},
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "repo_profile" in result["error_message"]


# ===========================================================================
# plan_node
# ===========================================================================
class TestPlanNode:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        case_input = _make_case_input()
        intent_graph = _make_intent_graph()
        repo_profile = _make_repo_profile()
        generation_plan = _make_generation_plan()
        container = _make_container()
        with patch("ddk.graph.nodes.plan.GenerationPlanner") as mock_planner:
            instance = mock_planner.return_value
            instance.plan = AsyncMock(return_value=generation_plan)
            result = await plan_node(
                {
                    "case_id": "C-001",
                    "case_input": case_input,
                    "intent_graph": intent_graph,
                    "repo_profile": repo_profile,
                },
                context=container,
            )

        assert result["current_node"] == "plan"
        assert result["generation_plan"] is generation_plan

    @pytest.mark.asyncio
    async def test_missing_container(self) -> None:
        result = await plan_node(
            {
                "case_id": "C-001",
                "case_input": _make_case_input(),
                "intent_graph": _make_intent_graph(),
                "repo_profile": _make_repo_profile(),
            },
        )
        assert result["terminal_state"] == "manual-review-required"

    @pytest.mark.asyncio
    async def test_container_with_none_llm(self) -> None:
        container = _make_container()
        container.llm = None
        result = await plan_node(
            {
                "case_id": "C-001",
                "case_input": _make_case_input(),
                "intent_graph": _make_intent_graph(),
                "repo_profile": _make_repo_profile(),
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"

    @pytest.mark.asyncio
    async def test_missing_upstream_state(self) -> None:
        container = _make_container()
        result = await plan_node(
            {
                "case_id": "C-001",
                "case_input": None,
                "intent_graph": None,
                "repo_profile": None,
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "intent_graph" in result["error_message"]


# ===========================================================================
# repo_scan_node
# ===========================================================================
class TestRepoScanNode:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        case_input = _make_case_input()
        profile = _make_repo_profile()
        container = _make_container()
        with patch("ddk.graph.nodes.repo_scan.RepoConventionScanner") as mock_scanner:
            instance = mock_scanner.return_value
            instance.scan = AsyncMock(return_value=profile)
            result = await repo_scan_node(
                {"case_input": case_input},
                context=container,
            )

        assert result["current_node"] == "repo_scan"
        assert result["repo_profile"] is profile

    @pytest.mark.asyncio
    async def test_missing_case_input(self) -> None:
        container = _make_container()
        result = await repo_scan_node({"case_input": None}, context=container)
        assert result["terminal_state"] == "manual-review-required"
        assert "case_input" in result["error_message"]

    @pytest.mark.asyncio
    async def test_works_without_container(self) -> None:
        """repo_scan_node passes llm=None to scanner when container is absent."""
        case_input = _make_case_input()
        profile = _make_repo_profile()
        with patch("ddk.graph.nodes.repo_scan.RepoConventionScanner") as mock_scanner:
            instance = mock_scanner.return_value
            instance.scan = AsyncMock(return_value=profile)
            result = await repo_scan_node({"case_input": case_input})

        assert result["current_node"] == "repo_scan"
        mock_scanner.assert_called_once_with(
            llm=None,
            model=DEFAULT_LIGHT_MODEL,
        )


# ===========================================================================
# generate_node
# ===========================================================================
class TestGenerateNode:
    @pytest.mark.asyncio
    async def test_happy_path(self, tmp_path: Path) -> None:
        case_input = _make_case_input()
        image = tmp_path / "img.png"
        image.write_bytes(b"png")
        case_input.image_paths = [image]
        case_input.repo_path = tmp_path
        intent_graph = _make_intent_graph()
        repo_profile = _make_repo_profile()
        plan = _make_generation_plan()
        artifacts = _make_artifacts()
        container = _make_container()
        with patch("ddk.graph.nodes.generate.CodeGenerator") as mock_gen:
            instance = mock_gen.return_value
            instance.generate_all = AsyncMock(return_value=artifacts)
            result = await generate_node(
                {
                    "case_input": case_input,
                    "intent_graph": intent_graph,
                    "repo_profile": repo_profile,
                    "generation_plan": plan,
                },
                context=container,
            )

        assert result["current_node"] == "generate"
        assert result["generated_artifacts"] is artifacts

    @pytest.mark.asyncio
    async def test_missing_container(self) -> None:
        result = await generate_node(
            {
                "case_input": _make_case_input(),
                "intent_graph": _make_intent_graph(),
                "repo_profile": _make_repo_profile(),
                "generation_plan": _make_generation_plan(),
            },
        )
        assert result["terminal_state"] == "manual-review-required"

    @pytest.mark.asyncio
    async def test_missing_multiple_upstream(self) -> None:
        container = _make_container()
        result = await generate_node(
            {
                "case_input": None,
                "intent_graph": None,
                "repo_profile": None,
                "generation_plan": None,
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        for key in ("generation_plan", "repo_profile", "intent_graph", "case_input"):
            assert key in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_single_upstream(self) -> None:
        container = _make_container()
        result = await generate_node(
            {
                "case_input": _make_case_input(),
                "intent_graph": _make_intent_graph(),
                "repo_profile": _make_repo_profile(),
                "generation_plan": None,
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "generation_plan" in result["error_message"]


# ===========================================================================
# normalize_node
# ===========================================================================
class TestNormalizeNode:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        artifacts = _make_artifacts()
        repo_profile = _make_repo_profile()
        report = MagicMock()
        patched = MagicMock()
        container = _make_container()
        with patch("ddk.graph.nodes.normalize.OutputNormalizer") as mock_norm:
            instance = mock_norm.return_value
            instance.normalize = AsyncMock(return_value=(report, patched))
            result = await normalize_node(
                {
                    "generated_artifacts": artifacts,
                    "repo_profile": repo_profile,
                },
                context=container,
            )

        assert result["current_node"] == "normalize"
        assert result["normalization_report"] is report
        assert result["generated_artifacts"] is patched

    @pytest.mark.asyncio
    async def test_missing_container(self) -> None:
        result = await normalize_node(
            {
                "generated_artifacts": _make_artifacts(),
                "repo_profile": _make_repo_profile(),
            },
        )
        assert result["terminal_state"] == "manual-review-required"

    @pytest.mark.asyncio
    async def test_missing_artifacts(self) -> None:
        container = _make_container()
        result = await normalize_node(
            {
                "generated_artifacts": None,
                "repo_profile": _make_repo_profile(),
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "generated_artifacts" in result["error_message"]

    @pytest.mark.asyncio
    async def test_missing_repo_profile(self) -> None:
        container = _make_container()
        result = await normalize_node(
            {
                "generated_artifacts": _make_artifacts(),
                "repo_profile": None,
            },
            context=container,
        )
        assert result["terminal_state"] == "manual-review-required"
        assert "repo_profile" in result["error_message"]

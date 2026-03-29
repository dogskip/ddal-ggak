"""Integration test — full 9-node pipeline E2E with FakeLLMAdapter.

Pipeline under test:
    START → intake → repo_scan → intent_extract → design_system → plan
    → generate → normalize → validate → [router] → END

All LLM calls are intercepted by FakeLLMAdapter.  No real API keys required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.screenshot_diff import SSIMResult
from ddk.graph.builder import build_ddk_graph
from ddk.graph.context import ServiceContainer
from ddk.graph.state import initial_state
from ddk.models.input import CaseInput
from ddk.models.validation import RuntimeValidationReport
from tests.fakes import FakeLLMAdapter, FakePlaywrightAdapter, InMemoryFilesystem
from tests.fakes.fake_sandbox import TempDirSandbox

# ---------------------------------------------------------------------------
# FakeLLMAdapter response fixtures
#
# Key derivation: first word of system prompt (lowercased).
#   "you"     → SemanticIntentExtractor  ("You are an expert UI analyst...")
#   "analyze" → DesignSystemInferencer   ("Analyze UI screenshots...")
#   "senior"  → GenerationPlanner        ("Senior React architect here...")
#
# RepoConventionScanner also starts with "You are a senior front-end developer…"
# but only calls LLM when framework=="other".  The test fixture below sets a
# package.json with React so static detection returns framework="react",
# bypassing any LLM call in that node.
# ---------------------------------------------------------------------------

_INTENT_GRAPH_RESPONSE = json.dumps(
    {
        "layout_regions": [],
        "components": [],
        "interactions": [],
        "unresolved_items": [],
        "confidence": 0.9,
    }
)

_DESIGN_SYSTEM_RESPONSE = json.dumps(
    {
        "inferred_tokens": [],
        "primitive_components": ["Button", "Card"],
        "token_source": "llm",
    }
)

_GENERATION_PLAN_RESPONSE = json.dumps(
    {
        "nodes": [],
        "execution_order": [],
        "target_files": [],
        "validation_hooks": [],
        "estimated_node_count": 0,
    }
)

# Phase 3 nodes — placeholders removed for Red phase; restored when Green phase complete

_GENERATED_NODE_RESPONSE = json.dumps(
    {
        "files": [],
        "file_map": {},
        "generation_trace": [],
        "changed_paths": [],
    }
)

_NORMALIZATION_RESPONSE = json.dumps(
    {
        "convention_fixes": [],
        "unresolved_drift": [],
        "patched_files": {},
    }
)


class _PassingRuntimeValidator:
    async def run(
        self,
        state: dict[str, object],
        **_: object,
    ) -> tuple[RuntimeValidationReport, None]:
        return (
            RuntimeValidationReport(
                case_id=str(state["case_id"]),
                build_success=True,
                type_check_success=True,
                lint_success=True,
            ),
            None,
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def repo_path(tmp_path: Path) -> Path:
    """Minimal React repo so repo_scan does NOT need LLM supplementation."""
    pkg = {
        "name": "test-shop-app",
        "dependencies": {"react": "^18.3.0", "react-dom": "^18.3.0"},
        "devDependencies": {"typescript": "^5.0.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    return tmp_path


@pytest.fixture()
def sample_input(repo_path: Path) -> CaseInput:
    """CaseInput with a real (minimal) PNG binary so image hashing succeeds."""
    img = repo_path / "design.png"
    # Minimal valid-looking PNG header bytes
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return CaseInput(
        case_id="C-INTEGRATION-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지 컴포넌트 생성",
        repo_path=repo_path,
    )


@pytest.fixture()
def pipeline_fake_llm() -> FakeLLMAdapter:
    """FakeLLMAdapter wired with canned JSON for all LLM-calling service nodes."""
    return FakeLLMAdapter(
        responses={
            "you": _INTENT_GRAPH_RESPONSE,  # SemanticIntentExtractor
            "analyze": _DESIGN_SYSTEM_RESPONSE,  # DesignSystemInferencer
            "senior": _GENERATION_PLAN_RESPONSE,  # GenerationPlanner
            "generate": _GENERATED_NODE_RESPONSE,  # CodeGenerator
            "normalize": _NORMALIZATION_RESPONSE,  # OutputNormalizer
        }
    )


@pytest.fixture()
def service_container(
    pipeline_fake_llm: FakeLLMAdapter,
    tmp_path: Path,
) -> ServiceContainer:
    """Full ServiceContainer with fake adapters — no real I/O."""
    git_stub = MagicMock()
    git_stub.status = MagicMock(return_value={})
    git_stub.diff = MagicMock(return_value="")
    git_stub.log = MagicMock(return_value=[])
    git_stub.create_worktree = AsyncMock()
    git_stub.remove_worktree = AsyncMock()
    git_stub.create_checkpoint = AsyncMock(return_value="ref-001")
    git_stub.rollback_to = AsyncMock()

    build_stub = MagicMock()
    build_stub.run = AsyncMock(
        return_value=BuildResult(success=True, stdout="", stderr="", returncode=0)
    )

    ss_stub = MagicMock()
    ss_stub.compute_ssim = MagicMock(return_value=SSIMResult(score=1.0, mismatch_regions=[]))
    ss_stub.generate_diff_image = MagicMock(return_value=tmp_path / "diff.png")

    return ServiceContainer(
        llm=pipeline_fake_llm,
        filesystem=InMemoryFilesystem(),
        git=git_stub,
        sandbox=TempDirSandbox(),
        build_runner=build_stub,
        browser=FakePlaywrightAdapter(),
        screenshot_diff=ss_stub,
        runtime_validator=_PassingRuntimeValidator(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestionPipeline:
    """E2E integration tests for the full certification pipeline."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_end_to_end(
        self,
        sample_input: CaseInput,
        service_container: ServiceContainer,
    ) -> None:
        """Full 9-node pipeline runs end-to-end and produces required outputs.

        Verifies:
        - Pipeline runs to completion without errors
        - repo_profile, intent_graph, generation_plan are all non-None
        - terminal_state is "ready" after certification
        - current_node is "certify" (final executed node before END)
        """
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container)

        # --- Basic structural assertions ---
        assert result is not None
        assert result["case_id"] == "C-INTEGRATION-001"

        # --- Phase 2 required outputs (D-08) ---
        assert result["repo_profile"] is not None, "repo_scan_node must populate repo_profile"
        assert result["intent_graph"] is not None, "intent_extract_node must populate intent_graph"
        assert result["generation_plan"] is not None, "plan_node must populate generation_plan"

        # --- No error state ---
        assert result.get("terminal_state") == "ready"
        assert result["scorecard"] is not None
        assert result["release_decision"] is not None
        assert result["evidence_pack"] is not None
        assert result["release_decision"].decision == "ready"

        # --- Pipeline reached the final node ---
        assert result["current_node"] == "certify"

    @pytest.mark.asyncio
    async def test_pipeline_preserves_case_id(
        self,
        sample_input: CaseInput,
        service_container: ServiceContainer,
    ) -> None:
        """case_id in initial state must be preserved throughout the pipeline."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container)

        assert result["case_id"] == sample_input.case_id

    @pytest.mark.asyncio
    async def test_pipeline_repo_profile_has_framework(
        self,
        sample_input: CaseInput,
        service_container: ServiceContainer,
    ) -> None:
        """repo_scan_node must detect 'react' from package.json statically."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container)

        assert result["repo_profile"] is not None
        assert result["repo_profile"].framework == "react"

    @pytest.mark.asyncio
    async def test_pipeline_generation_plan_has_case_id(
        self,
        sample_input: CaseInput,
        service_container: ServiceContainer,
    ) -> None:
        """GenerationPlan must have case_id injected from pipeline state."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container)

        assert result["generation_plan"] is not None
        assert result["generation_plan"].case_id == "C-INTEGRATION-001"

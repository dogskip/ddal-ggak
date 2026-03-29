"""E2E integration tests for the 9-node generation pipeline.

Pipeline under test:
    START → intake → repo_scan → intent_extract → design_system → plan
    → generate → normalize → validate → [router] → END

All LLM calls are intercepted by FakeLLMAdapter.  No real API keys required.
The generation plan includes one real node (node-btn) so both generate_node and
normalize_node make their LLM calls, producing non-None generated_artifacts and
normalization_report in the final state.
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
#   "you"       → SemanticIntentExtractor  ("You are an expert UI analyst...")
#   "analyze"   → DesignSystemInferencer   ("Analyze UI screenshots...")
#   "senior"    → GenerationPlanner        ("Senior React architect here...")
#   "generate"  → CodeGenerator            ("Generate production-quality React/TypeScript...")
#   "normalize" → OutputNormalizer         ("Normalize convention violations...")
#
# RepoConventionScanner only calls LLM when framework=="other".
# The test fixture sets a package.json with React so static detection returns
# framework="react", bypassing any LLM call in repo_scan.
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
        "nodes": [
            {
                "id": "node-btn",
                "node_type": "component",
                "target_path": "src/components/Button.tsx",
                "dependencies": [],
                "validation_hooks": [],
                "repair_hooks": [],
            }
        ],
        "execution_order": ["node-btn"],
        "target_files": ["src/components/Button.tsx"],
        "validation_hooks": [],
        "estimated_node_count": 1,
    }
)

_GENERATED_NODE_RESPONSE = json.dumps(
    {
        "files": [
            {
                "path": "src/components/Button.tsx",
                "content": "export const Button = () => <button>Click</button>;",
                "language": "typescript",
                "source_node_id": "node-btn",
                "is_new": True,
            }
        ],
        "entry_point": "src/components/Button.tsx",
        "component_exports": ["Button"],
    }
)

_NORMALIZATION_RESPONSE = json.dumps(
    {
        "convention_fixes": [
            {
                "fix_type": "naming",
                "file_path": "src/components/Button.tsx",
                "rule_id": "NAMING-001",
                "description": "OK",
                "before_snippet": "",
                "after_snippet": "",
                "severity": "nice-to-have",
            }
        ],
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
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return CaseInput(
        case_id="C-GEN-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지 컴포넌트 생성",
        repo_path=repo_path,
    )


@pytest.fixture()
def service_container_7node(
    repo_path: Path,
    tmp_path: Path,
) -> ServiceContainer:
    """Full ServiceContainer wired with FakeLLMAdapter for all 5 LLM-calling nodes."""
    fake_llm = FakeLLMAdapter(
        responses={
            "you": _INTENT_GRAPH_RESPONSE,  # SemanticIntentExtractor
            "analyze": _DESIGN_SYSTEM_RESPONSE,  # DesignSystemInferencer
            "senior": _GENERATION_PLAN_RESPONSE,  # GenerationPlanner
            "generate": _GENERATED_NODE_RESPONSE,  # CodeGenerator
            "normalize": _NORMALIZATION_RESPONSE,  # OutputNormalizer
        }
    )

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
        llm=fake_llm,
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


class TestNineNodePipeline:
    """E2E integration tests for the full certification pipeline."""

    @pytest.mark.asyncio
    async def test_seven_node_pipeline_end_to_end(
        self,
        sample_input: CaseInput,
        service_container_7node: ServiceContainer,
    ) -> None:
        """Full 9-node pipeline runs end-to-end and produces required outputs.

        Verifies:
        - Pipeline runs to completion without errors
        - result is not None
        - terminal_state is "ready" after certification
        - case_id is preserved
        """
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container_7node)

        assert result is not None
        assert result["case_id"] == "C-GEN-001"
        assert result.get("terminal_state") == "ready"
        assert result["scorecard"] is not None
        assert result["release_decision"] is not None
        assert result["evidence_pack"] is not None
        assert result["release_decision"].decision == "ready"

    @pytest.mark.asyncio
    async def test_pipeline_produces_generated_artifacts(
        self,
        sample_input: CaseInput,
        service_container_7node: ServiceContainer,
    ) -> None:
        """generate_node must populate generated_artifacts with file(s).

        Verifies:
        - generated_artifacts is not None after full pipeline run
        - generated_artifacts.files contains the Button.tsx file
        """
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container_7node)

        assert result["generated_artifacts"] is not None, (
            "generate_node must populate generated_artifacts"
        )
        assert len(result["generated_artifacts"].files) == 1
        assert result["generated_artifacts"].files[0].path == "src/components/Button.tsx"

    @pytest.mark.asyncio
    async def test_pipeline_produces_normalization_report(
        self,
        sample_input: CaseInput,
        service_container_7node: ServiceContainer,
    ) -> None:
        """normalize_node must populate normalization_report.

        Verifies:
        - normalization_report is not None after full pipeline run
        - normalization_report.case_id matches the pipeline's case_id
        - normalization_report contains convention_fixes from the fake response
        """
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container_7node)

        assert result["normalization_report"] is not None, (
            "normalize_node must populate normalization_report"
        )
        assert result["normalization_report"].case_id == "C-GEN-001"
        assert len(result["normalization_report"].convention_fixes) == 1

    @pytest.mark.asyncio
    async def test_pipeline_reaches_normalize_node(
        self,
        sample_input: CaseInput,
        service_container_7node: ServiceContainer,
    ) -> None:
        """Pipeline must reach certify before routing to END.

        Verifies:
        - current_node == "certify" after successful certification
        """
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container_7node)

        assert result["current_node"] == "certify", (
            f"Expected final node 'certify', got '{result['current_node']}'"
        )
        assert result["evidence_pack"].terminal_state == "ready"

    @pytest.mark.asyncio
    async def test_pipeline_preserves_case_id(
        self,
        sample_input: CaseInput,
        service_container_7node: ServiceContainer,
    ) -> None:
        """case_id in initial state must be preserved throughout all 7 nodes."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)

        result = await compiled.ainvoke(state, context=service_container_7node)

        assert result["case_id"] == sample_input.case_id
        # generated_artifacts also carries case_id (set by CodeGenerator from plan.case_id)
        if result["generated_artifacts"] is not None:
            assert result["generated_artifacts"].case_id == sample_input.case_id

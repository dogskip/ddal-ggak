"""Integration smoke test — LangGraph StateGraph + ServiceContainer DI wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.graph.builder import build_ddk_graph
from ddk.graph.context import ServiceContainer
from ddk.graph.state import initial_state
from ddk.models.input import CaseInput


@pytest.fixture()
def sample_input(tmp_path: Path) -> CaseInput:
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG")
    return CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지",
        repo_path=tmp_path,
    )


@pytest.fixture()
def service_container(tmp_path: Path) -> ServiceContainer:
    """Build a ServiceContainer with all fakes."""
    from unittest.mock import AsyncMock, MagicMock  # noqa: PLC0415

    from ddk.adapters.build_runner import BuildResult  # noqa: PLC0415
    from ddk.adapters.screenshot_diff import SSIMResult  # noqa: PLC0415
    from tests.fakes.fake_filesystem import InMemoryFilesystem  # noqa: PLC0415
    from tests.fakes.fake_llm_adapter import FakeLLMAdapter  # noqa: PLC0415
    from tests.fakes.fake_playwright_adapter import FakePlaywrightAdapter  # noqa: PLC0415
    from tests.fakes.fake_sandbox import TempDirSandbox  # noqa: PLC0415

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
        llm=FakeLLMAdapter(),
        filesystem=InMemoryFilesystem(),
        git=git_stub,
        sandbox=TempDirSandbox(),
        build_runner=build_stub,
        browser=FakePlaywrightAdapter(),
        screenshot_diff=ss_stub,
    )


class TestDISmoke:
    def test_build_ddk_graph_returns_state_graph(self) -> None:
        """build_ddk_graph() must return a LangGraph StateGraph (not compiled)."""
        from langgraph.graph import StateGraph  # noqa: PLC0415

        graph = build_ddk_graph()
        assert isinstance(graph, StateGraph)

    def test_state_graph_compiles(self) -> None:
        """StateGraph must compile without errors."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        assert compiled is not None

    @pytest.mark.asyncio
    async def test_graph_invoke_skeleton(self, sample_input: CaseInput) -> None:
        """Skeleton graph must run to completion with no errors."""
        graph = build_ddk_graph()
        compiled = graph.compile()
        state = initial_state(sample_input)
        result = await compiled.ainvoke(state)
        assert result is not None
        assert result["case_id"] == "C-001"

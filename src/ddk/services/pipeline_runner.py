"""Pipeline runner for Phase 5 CLI execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.filesystem import FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.llm.recording import RecordingLLMAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.preview import PreviewLauncher
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter
from ddk.graph.context import ServiceContainer
from ddk.graph.state import initial_state
from ddk.models.config import DEFAULT_LIGHT_MODEL, DEFAULT_PRIMARY_MODEL
from ddk.models.input import CaseInput
from ddk.services.auto_fix_planner import AutoFixPlanner
from ddk.services.failure_classifier import FailureClassifier
from ddk.services.rollback_controller import RollbackController
from ddk.services.runtime_validator import RuntimeValidator

StageCallback = Callable[[str, dict[str, Any]], None]


async def _stream(
    compiled: Any, state: Any, container: ServiceContainer, on_update: StageCallback
) -> dict[str, Any]:
    """Run the compiled graph, report each stage as it finishes, return the final state."""
    result: dict[str, Any] = {}
    async for mode, chunk in compiled.astream(
        state, context=container, stream_mode=["updates", "values"]
    ):
        if mode == "values":
            result = cast(dict[str, Any], chunk)
            continue
        for stage, update in cast(dict[str, Any], chunk).items():
            on_update(str(stage), cast(dict[str, Any], update or {}))
    return result


@dataclass
class RuntimeServices:
    """Concrete runtime dependencies needed to execute the graph."""

    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    sandbox: SandboxAdapter
    build_runner: BuildRunner
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter
    primary_model: str = DEFAULT_PRIMARY_MODEL
    light_model: str = DEFAULT_LIGHT_MODEL
    install_dependencies: bool = False
    step_timeout_s: int = 300
    max_fix_attempts: int = 3
    cassette_path: Path | None = None
    preview: PreviewLauncher | None = None
    ssim_threshold: float = 0.92
    max_mismatch_ratio: float = 0.03


class PipelineRunner:
    """Execute the full ddalggak graph for a single case input."""

    def __init__(self, services: RuntimeServices) -> None:
        self._services = services

    async def run_case(
        self,
        case_input: CaseInput,
        *,
        case_dir: Path | None = None,
        on_update: StageCallback | None = None,
    ) -> dict[str, Any]:
        """Run the graph end-to-end and return the final graph state.

        ``case_dir`` is where screenshots of the rendered page are kept; it defaults to
        ``<repo>/.ddk/cases/<case_id>``. ``on_update(stage, update)`` is called as each stage
        finishes, with what that stage returned.
        """
        try:
            return await self._run_case(case_input, case_dir, on_update)
        finally:
            await self._services.browser.close()

    async def _run_case(
        self, case_input: CaseInput, case_dir: Path | None, on_update: StageCallback | None
    ) -> dict[str, Any]:
        case_root = case_dir or Path(case_input.repo_path) / ".ddk" / "cases" / case_input.case_id
        llm = RecordingLLMAdapter(self._services.llm, cassette_path=self._services.cassette_path)
        rollback_controller = RollbackController(
            git=self._services.git,
            repo_path=Path(case_input.repo_path),
        )
        runtime_validator = RuntimeValidator(
            sandbox=self._services.sandbox,
            build_runner=self._services.build_runner,
            playwright=self._services.browser,
            screenshot_diff=self._services.screenshot_diff,
            classifier=FailureClassifier(),
            install_dependencies=self._services.install_dependencies,
            step_timeout_s=self._services.step_timeout_s,
            preview=self._services.preview,
            visual_dir=case_root / "artifacts" / "visual",
            ssim_threshold=self._services.ssim_threshold,
            max_mismatch_ratio=self._services.max_mismatch_ratio,
        )
        container = ServiceContainer(
            llm=llm,
            filesystem=self._services.filesystem,
            git=self._services.git,
            sandbox=self._services.sandbox,
            build_runner=self._services.build_runner,
            browser=self._services.browser,
            screenshot_diff=self._services.screenshot_diff,
            primary_model=self._services.primary_model,
            light_model=self._services.light_model,
            runtime_validator=runtime_validator,
            auto_fix_planner=AutoFixPlanner(
                llm=llm,
                model=self._services.primary_model,
                repo_root=Path(case_input.repo_path),
            ),
            failure_classifier=FailureClassifier(),
            rollback_controller=rollback_controller,
        )
        builder_module = import_module("ddk.graph.builder")
        build_graph = cast(Callable[[], Any], builder_module.build_ddk_graph)  # type: ignore[union-attr]
        compiled = build_graph().compile()
        state = initial_state(case_input, retry_budget=self._services.max_fix_attempts)
        if on_update is None:
            result = cast(dict[str, Any], await compiled.ainvoke(state, context=container))
        else:
            result = await _stream(compiled, state, container, on_update)
        llm.save()
        return {**result, "llm_calls": llm.export()}

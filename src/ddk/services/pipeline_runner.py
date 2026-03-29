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
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter
from ddk.graph.context import ServiceContainer
from ddk.graph.state import initial_state
from ddk.models.input import CaseInput
from ddk.services.auto_fix_planner import AutoFixPlanner
from ddk.services.failure_classifier import FailureClassifier
from ddk.services.rollback_controller import RollbackController
from ddk.services.runtime_validator import RuntimeValidator


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


class PipelineRunner:
    """Execute the full ddalggak graph for a single case input."""

    def __init__(self, services: RuntimeServices) -> None:
        self._services = services

    async def run_case(self, case_input: CaseInput) -> dict[str, Any]:
        """Run the graph end-to-end and return the final graph state."""
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
        )
        container = ServiceContainer(
            llm=self._services.llm,
            filesystem=self._services.filesystem,
            git=self._services.git,
            sandbox=self._services.sandbox,
            build_runner=self._services.build_runner,
            browser=self._services.browser,
            screenshot_diff=self._services.screenshot_diff,
            runtime_validator=runtime_validator,
            auto_fix_planner=AutoFixPlanner(llm=self._services.llm),
            failure_classifier=FailureClassifier(),
            rollback_controller=rollback_controller,
        )
        builder_module = import_module("ddk.graph.builder")
        build_graph = cast(Callable[[], Any], builder_module.build_ddk_graph)  # type: ignore[union-attr]
        compiled = build_graph().compile()
        result = await compiled.ainvoke(initial_state(case_input), context=container)
        return cast(dict[str, Any], result)

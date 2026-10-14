"""ServiceContainer DI container for LangGraph context_schema injection — INFRA-04."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.filesystem import FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter
from ddk.models.config import DEFAULT_LIGHT_MODEL, DEFAULT_PRIMARY_MODEL

if TYPE_CHECKING:
    from ddk.services.auto_fix_planner import AutoFixPlanner
    from ddk.services.context_pack_builder import ContextPackBuilder
    from ddk.services.design_system_inferencer import DesignSystemInferencer
    from ddk.services.failure_classifier import FailureClassifier
    from ddk.services.generation_planner import GenerationPlanner
    from ddk.services.intake_processor import IntakeProcessor
    from ddk.services.repo_convention_scanner import RepoConventionScanner
    from ddk.services.rollback_controller import RollbackController
    from ddk.services.runtime_validator import RuntimeValidator
    from ddk.services.semantic_intent_extractor import SemanticIntentExtractor


@dataclass
class ServiceContainer:
    """Run-scoped DI container holding all 7 adapter Protocol instances + 6 domain services.

    Injected into every LangGraph node via::

        workflow = StateGraph(GraphState, context_schema=ServiceContainer)
        graph = workflow.compile()
        result = await graph.ainvoke(state, context=container)

    Inside a node, services are accessed via ``runtime.context``:

        async def my_node(state: GraphState, **kwargs) -> dict:
            # LangGraph injects context via **kwargs in future releases
            ...
    """

    # Phase 1 adapters (required)
    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    sandbox: SandboxAdapter
    build_runner: BuildRunner
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter
    primary_model: str = DEFAULT_PRIMARY_MODEL
    light_model: str = DEFAULT_LIGHT_MODEL

    # Phase 2 services (optional — populated when pipeline runs)
    intake_processor: IntakeProcessor | None = None
    repo_convention_scanner: RepoConventionScanner | None = None
    semantic_intent_extractor: SemanticIntentExtractor | None = None
    design_system_inferencer: DesignSystemInferencer | None = None
    generation_planner: GenerationPlanner | None = None
    context_pack_builder: ContextPackBuilder | None = None

    # Phase 4 services (optional — populated for validation/self-healing pipeline)
    runtime_validator: RuntimeValidator | None = None
    auto_fix_planner: AutoFixPlanner | None = None
    failure_classifier: FailureClassifier | None = None
    rollback_controller: RollbackController | None = None


def primary_model_from(container: object | None) -> str:
    value = getattr(container, "primary_model", None)
    return value if isinstance(value, str) else DEFAULT_PRIMARY_MODEL


def light_model_from(container: object | None) -> str:
    value = getattr(container, "light_model", None)
    return value if isinstance(value, str) else DEFAULT_LIGHT_MODEL

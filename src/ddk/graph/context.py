"""ServiceContainer DI container for LangGraph context_schema injection — INFRA-04."""

from __future__ import annotations

from dataclasses import dataclass

from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.filesystem import FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter


@dataclass
class ServiceContainer:
    """Run-scoped DI container holding all 7 adapter Protocol instances.

    Injected into every LangGraph node via::

        workflow = StateGraph(GraphState, context_schema=ServiceContainer)
        graph = workflow.compile()
        result = await graph.ainvoke(state, context=container)

    Inside a node, services are accessed via ``runtime.context``:

        async def my_node(state: GraphState, **kwargs) -> dict:
            # LangGraph injects context via **kwargs in future releases
            ...
    """

    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    sandbox: SandboxAdapter
    build_runner: BuildRunner
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter

"""Repo scan node — thin adapter for RepoConventionScanner (D-05)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.repo_convention_scanner import RepoConventionScanner


async def repo_scan_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Scan repository conventions and produce RepoProfile.

    Thin adapter: reads state, calls RepoConventionScanner, writes state (D-05).
    No business logic in node.
    """
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container else None
    scanner = RepoConventionScanner(llm=llm)
    case_input = state.get("case_input")
    if case_input is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "Missing upstream state: case_input",
        }
    profile = await scanner.scan(case_input.repo_path)
    return {
        "repo_profile": profile,
        "current_node": "repo_scan",
    }

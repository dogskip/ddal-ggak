"""GenerationPlanner — creates ordered GenerationPlan from intent + profile (INGEST-06)."""

from __future__ import annotations

import json
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models.generation import GenerationPlan
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile

_SYSTEM_PROMPT = """Senior React architect here. Given a UI intent graph and repository profile, create a precise GenerationPlan that describes exactly which files to create or modify.

## Planning Rules

1. **Target files must be specific**: Use exact paths relative to repo root.
2. **Respect repo conventions**: Follow the NamingRules and FileLayoutRules from RepoProfile exactly.
3. **Topological ordering**: List nodes in dependency order (types first, then components, then pages, then tests).
4. **Minimal changes**: Only include files that are necessary. Do not generate test files unless explicitly requested.
5. **Reuse existing**: If an existing component matches, reference it instead of generating a duplicate.

## Node Types
- `type`: TypeScript interface/type definition file
- `component`: React component (.tsx)
- `hook`: React custom hook
- `style`: CSS module or style file
- `route`: Page-level component (Next.js page, React Router route)
- `test`: Test file (.test.tsx)
- `file`: Generic file

Output a complete GenerationPlan JSON with execution_order sorted topologically."""


class GenerationPlanner:
    """Creates topologically ordered GenerationPlan for code generation (INGEST-06)."""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=3072,
        )

    async def plan(
        self,
        case_id: str,
        intent_graph: IntentGraph,
        repo_profile: RepoProfile,
        user_prompt: str,
    ) -> GenerationPlan:
        """Generate a code generation plan from intent + profile.

        Args:
            case_id: Case identifier.
            intent_graph: Extracted UI intent.
            repo_profile: Repository conventions.
            user_prompt: Original user request.

        Returns:
            GenerationPlan with topologically ordered nodes.
        """
        user_content = (
            f"Create a GenerationPlan for this UI.\n\n"
            f"## User Intent\n{user_prompt}\n\n"
            f"## Intent Graph (summary)\n"
            f"- Layout regions: {len(intent_graph.layout_regions)}\n"
            f"- Components: {len(intent_graph.components)}\n"
            f"- Interactions: {len(intent_graph.interactions)}\n"
            f"- Confidence: {intent_graph.confidence}\n"
            f"{intent_graph.model_dump_json(indent=2)[:3000]}\n\n"
            f"## Repository Profile\n"
            f"{repo_profile.model_dump_json(indent=2)}\n\n"
            f"Output the complete GenerationPlan JSON."
        )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response: LLMResponse = await self._llm.complete_structured(
            messages, self._config, output_schema=GenerationPlan
        )

        data: dict[str, Any] = json.loads(response.content)
        data["case_id"] = case_id
        nodes_data = data.get("nodes", [])
        # Populate execution_order from node IDs if not provided by LLM
        if not data.get("execution_order"):
            data["execution_order"] = [n.get("id", "") for n in nodes_data]
        # Collect unique target_files from all node target_path values
        if not data.get("target_files"):
            data["target_files"] = list(
                dict.fromkeys(
                    n.get("target_path", "")
                    for n in nodes_data
                    if n.get("target_path")
                )
            )
        # Set estimated_node_count to match nodes length
        data["estimated_node_count"] = len(nodes_data)

        return GenerationPlan.model_validate(data)

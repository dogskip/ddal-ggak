"""CodeGenerator service — Phase 3 (GEN-01).

Responsible for iterating over a GenerationPlan's execution_order and calling the
LLM once per node to produce React/TypeScript source files.

Key contract:
- One LLM call per node in plan.execution_order; empty plan → 0 LLM calls
- Returns GeneratedArtifactSet with case_id, files, file_map (path→content), generation_trace
- generation_trace entries are formatted as "{node_id}:{node.target_path}"
- System prompt starts with "Generate" so FakeLLMAdapter routes to key "generate"
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.generation import (
    GeneratedArtifactSet,
    GeneratedFile,
    GenerationPlan,
)
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — MUST start with "Generate" so FakeLLMAdapter routes to the
# "generate" key via:  msg.content.split()[0].lower() == "generate"
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
Generate React/TypeScript component code for the following planned node.

You will receive a JSON object describing a single component node.
Respond with a JSON object matching this schema:
{
  "files": [
    {
      "path": "<relative file path, e.g. src/components/Button.tsx>",
      "content": "<full TypeScript/TSX source code>",
      "language": "typescript"
    }
  ],
  "entry_point": "<path to main exported file, or null>",
  "component_exports": ["<exported component name>", ...]
}

Rules:
- Write idiomatic React 18 with TypeScript strict mode
- Use named exports; no default exports
- Respond with valid JSON only — no markdown fences, no commentary
"""


class _GeneratedNodeOutput(BaseModel):
    """Internal model for the LLM's per-node response."""

    files: list[dict[str, Any]] = []
    entry_point: str | None = None
    component_exports: list[str] = []


class CodeGenerator:
    """Calls the LLM once per planned node and assembles a GeneratedArtifactSet."""

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=4096,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_all(
        self,
        plan: GenerationPlan,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
    ) -> GeneratedArtifactSet:
        """Generate code for every node in plan.execution_order.

        Args:
            plan: The generation plan with ordered node list.
            repo_profile: Repository conventions used to guide the LLM.
            intent_graph: Semantic intent context (provided to LLM in user message).
            prompt: Original user prompt for context.

        Returns:
            GeneratedArtifactSet aggregating all generated files.
        """
        if not plan.execution_order:
            return GeneratedArtifactSet(
                case_id=plan.case_id,
                files=[],
                file_map={},
                generation_trace=[],
                changed_paths=[],
            )

        # Build id→node lookup from the list
        node_map = {node.id: node for node in plan.nodes}

        all_files: list[GeneratedFile] = []
        file_map: dict[str, str] = {}
        generation_trace: list[str] = []

        for node_id in plan.execution_order:
            node = node_map[node_id]
            node_output = await self._generate_node(
                node_id=node_id,
                node=node,
                repo_profile=repo_profile,
                intent_graph=intent_graph,
                prompt=prompt,
            )

            # Record trace entry: "{node_id}:{target_path}"
            generation_trace.append(f"{node_id}:{node.target_path}")

            for file_dict in node_output.files:
                path = file_dict["path"]
                content = file_dict.get("content", "")
                language = file_dict.get("language", "typescript")
                gf = GeneratedFile(
                    path=path,
                    content=content,
                    language=language,  # type: ignore[arg-type]
                    source_node_id=node_id,
                    is_new=file_dict.get("is_new", False),
                )
                all_files.append(gf)
                # file_map maps path → content string (not GeneratedFile)
                file_map[path] = content

        return GeneratedArtifactSet(
            case_id=plan.case_id,
            files=all_files,
            file_map=file_map,
            generation_trace=generation_trace,
            changed_paths=[f.path for f in all_files],
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _generate_node(
        self,
        node_id: str,
        node: Any,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
    ) -> _GeneratedNodeOutput:
        """Issue a single LLM call for one planned node."""
        user_content = json.dumps(
            {
                "node_id": node_id,
                "target_path": node.target_path,
                "node_type": node.node_type,
                "dependencies": node.dependencies,
                "repo_framework": repo_profile.framework,
                "user_prompt": prompt,
                "intent_summary": str(intent_graph),
            },
            ensure_ascii=False,
        )
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]
        response = await self._llm.complete(messages, self._config)
        try:
            data = json.loads(response.content)
            return _GeneratedNodeOutput(**data)
        except Exception:  # noqa: BLE001
            logger.warning("Code generation LLM response parsing failed", exc_info=True)
            return _GeneratedNodeOutput()

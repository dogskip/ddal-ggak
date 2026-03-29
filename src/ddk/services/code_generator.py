"""CodeGenerator — GenerationPlan → GeneratedArtifactSet (CODEGEN-01)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, LLMResponse, Message
from ddk.models._base import DDKBaseModel
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile, GenerationPlan
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile

# KEY: starts with "Generate" → FakeLLM key="generate".
# Do NOT change to "You are..." — that collides with SemanticIntentExtractor (key="you").
_SYSTEM_PROMPT = """Generate production-quality React/TypeScript code for a single file.

## Code Quality Rules
1. Use TypeScript with strict mode.
2. All props must have explicit types.
3. No `any` types.
4. Use the project's CSS approach as specified.
5. Import from existing components when available.
6. Component file structure:
   - imports (external libraries first, then internal)
   - type definitions
   - main component
   - export default
7. No placeholder comments like "// TODO: implement this".
8. The generated file must be complete and immediately functional.

## Response Format
Output structured JSON with a files array."""


class _GeneratedNodeOutput(DDKBaseModel):
    """Per-node LLM output schema. Internal to CodeGenerator only."""

    files: list[GeneratedFile]
    entry_point: str | None = None
    component_exports: list[str] = Field(default_factory=list)


class CodeGenerator:
    """Generates React/TypeScript files from a GenerationPlan (CODEGEN-01).

    Calls LLM once per node in execution_order (node-by-node, not batched).
    Model: claude-3-5-sonnet-20241022, temperature=0.0.
    """

    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=4096,
        )

    async def generate_all(
        self,
        plan: GenerationPlan,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
    ) -> GeneratedArtifactSet:
        """Generate all files defined in plan.execution_order.

        One LLM call per GenerationNode. Empty execution_order returns empty set
        without any LLM call.
        """
        if not plan.execution_order:
            return GeneratedArtifactSet(
                case_id=plan.case_id,
                files=[],
                file_map={},
                generation_trace=[],
                changed_paths=[],
            )

        all_files: list[GeneratedFile] = []
        trace_entries: list[str] = []
        node_map = {n.id: n for n in plan.nodes}

        for node_id in plan.execution_order:
            node = node_map[node_id]
            node_output = await self._generate_node(
                node_id=node_id,
                target_path=node.target_path,
                node_type=node.node_type,
                generation_prompt_hint=node.generation_prompt_hint,
                repo_profile=repo_profile,
                intent_graph=intent_graph,
                prompt=prompt,
            )
            for f in node_output.files:
                # Ensure source_node_id is set for traceability
                if not f.source_node_id:
                    all_files.append(f.model_copy(update={"source_node_id": node_id}))
                else:
                    all_files.append(f)
            trace_entries.append(f"{node_id}:{node.target_path}")

        file_map = {f.path: f.content for f in all_files}
        changed_paths = [f.path for f in all_files]

        return GeneratedArtifactSet(
            case_id=plan.case_id,
            files=all_files,
            file_map=file_map,
            generation_trace=trace_entries,
            changed_paths=changed_paths,
            total_tokens_used=0,  # future: accumulate from LLMResponse
        )

    async def _generate_node(
        self,
        node_id: str,
        target_path: str,
        node_type: str,
        generation_prompt_hint: str | None,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
    ) -> _GeneratedNodeOutput:
        """Generate a single file for one GenerationNode."""
        hint = generation_prompt_hint or ""
        user_content = (
            f"Generate the following file:\n\n"
            f"Target path: {target_path}\n"
            f"Node type: {node_type}\n"
            f"User intent: {prompt}\n"
            f"{f'Generation hint: {hint}' if hint else ''}\n\n"
            f"## Repository Profile\n"
            f"Framework: {repo_profile.framework}\n"
            f"{repo_profile.model_dump_json(indent=2)[:1500]}\n\n"
            f"Output a _GeneratedNodeOutput JSON with a files array containing the complete file."
        )

        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=user_content),
        ]

        response: LLMResponse = await self._llm.complete_structured(
            messages, self._config, output_schema=_GeneratedNodeOutput
        )

        data: dict[str, Any] = json.loads(response.content)
        return _GeneratedNodeOutput.model_validate(data)

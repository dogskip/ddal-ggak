"""CodeGenerator service — Phase 3 (GEN-01).

Walks a GenerationPlan's execution_order and calls the model once per node.

Key contract:
- One LLM call per node in plan.execution_order; empty plan → 0 LLM calls
- Every call carries the design image(s), the user's request, the extracted intent, the
  repository conventions and key files, and the files generated for earlier nodes
- The answer is a set of ``=== FILE: path ===`` blocks (a JSON ``files`` list is still read)
- An answer without a usable file, or one cut off by the token limit, is a ``GenerationError``
  that names the node; nothing is silently skipped
- Returns GeneratedArtifactSet with case_id, files, file_map (path→content), generation_trace
- generation_trace entries are formatted as "{node_id}:{node.target_path}"
- System prompt starts with "Generate" so FakeLLMAdapter routes to key "generate"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.adapters.llm.parsing import parse_llm_json
from ddk.exceptions import GenerationError
from ddk.models.config import DEFAULT_PRIMARY_MODEL
from ddk.models.context_pack import ContextPack
from ddk.models.generation import (
    GeneratedArtifactSet,
    GeneratedFile,
    GenerationNode,
    GenerationPlan,
)
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile
from ddk.security.repo_paths import (
    UnsafeRepositoryPathError,
    ensure_distinct_paths,
    normalize_change_path,
    read_source,
)
from ddk.services.file_blocks import language_of, parse_file_blocks

logger = logging.getLogger(__name__)

_MAX_TOKENS = 16_384
_INTENT_CHARS = 4000
_PROFILE_CHARS = 2500
_ORIGINAL_CHARS = 200_000

# System prompt — MUST start with "Generate" so FakeLLMAdapter routes to the "generate" key.
_SYSTEM_PROMPT = """\
Generate the source files for one planned node of a React/TypeScript UI so that the page looks \
like the attached reference design.

You get the node to build, the user's request, the intent extracted from the design, the \
repository's conventions and key files, and the files already generated for earlier nodes.

Rules:
- Match the design: layout, spacing, sizes, colors, fonts and the visible text of the image.
- Follow the repository: framework, styling approach, file layout and naming. Reuse existing \
components and tokens instead of writing duplicates.
- Import earlier generated files by their exact paths and exported names.
- TypeScript strict mode. No `any`, no `@ts-ignore`. Do not add dependencies and do not touch \
package.json, lockfiles, tsconfig or lint configuration.
- Answer with the complete content of every file this node creates or changes, each introduced \
by a line
=== FILE: relative/path.tsx ===
and nothing else: no explanation, no markdown fences, no JSON.
"""


class CodeGenerator:
    """Calls the LLM once per planned node and assembles a GeneratedArtifactSet."""

    def __init__(self, llm: LLMAdapter, model: str = DEFAULT_PRIMARY_MODEL) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model=model,
            temperature=0.0,
            max_tokens=_MAX_TOKENS,
            metadata={"purpose": "generate"},
        )

    async def generate_all(
        self,
        plan: GenerationPlan,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
        *,
        images: list[tuple[str, str]] | None = None,
        context: ContextPack | None = None,
        repo_root: Path | None = None,
    ) -> GeneratedArtifactSet:
        """Generate code for every node in plan.execution_order.

        Args:
            plan: The generation plan with ordered node list.
            repo_profile: Repository conventions used to guide the LLM.
            intent_graph: Semantic intent context.
            prompt: Original user prompt.
            images: Design images as ``(base64, media_type)``, sent with every node.
            context: Key files of the repository, read-only.
            repo_root: Used to tell new files from changed ones.

        Raises:
            GenerationError: a node produced no usable file or was cut off.
        """
        if not plan.execution_order:
            return GeneratedArtifactSet(case_id=plan.case_id, files=[])

        nodes = {node.id: node for node in plan.nodes}
        files: dict[str, GeneratedFile] = {}
        by_node: dict[str, list[str]] = {}
        trace: list[str] = []
        tokens = 0

        for node_id in plan.execution_order:
            node = nodes[node_id]
            user = _node_prompt(
                node, prompt, repo_profile, intent_graph, context, files, by_node, nodes
            )
            messages = [
                Message(role="system", content=_SYSTEM_PROMPT),
                Message(role="user", content=user, images=list(images) if images else None),
            ]
            response = await self._llm.complete(messages, self._config)
            tokens += response.input_tokens + response.output_tokens
            if response.truncated:
                raise GenerationError(
                    f"Node {node_id} ({node.target_path}): the model's answer was cut off at "
                    f"{self._config.max_tokens} tokens; split the node or raise the limit."
                )

            produced = _usable_files(response.content, node_id, repo_root)
            if not produced:
                raise GenerationError(
                    f"Node {node_id} ({node.target_path}): the model returned no usable file."
                )
            trace.append(f"{node_id}:{node.target_path}")
            by_node[node_id] = [f.path for f in produced]
            for generated in produced:
                files[generated.path] = generated

        ordered = list(files.values())
        return GeneratedArtifactSet(
            case_id=plan.case_id,
            files=ordered,
            file_map={f.path: f.content for f in ordered},
            generation_trace=trace,
            total_tokens_used=tokens,
            changed_paths=[f.path for f in ordered],
            trace={
                "images": len(images or []),
                "context_pack_hash": context.context_pack_hash if context else None,
            },
        )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def _node_prompt(
    node: GenerationNode,
    prompt: str,
    repo_profile: RepoProfile,
    intent_graph: IntentGraph,
    context: ContextPack | None,
    generated: dict[str, GeneratedFile],
    by_node: dict[str, list[str]],
    nodes: dict[str, GenerationNode],
) -> str:
    lines = [
        "## Node",
        f"id: {node.id}",
        f"type: {node.node_type}",
        f"target path: {node.target_path}",
    ]
    if node.dependencies:
        lines.append(
            "depends on: "
            + ", ".join(_describe_dependency(d, by_node, nodes) for d in node.dependencies)
        )
    if node.generation_prompt_hint:
        lines.append(f"hint: {node.generation_prompt_hint}")

    lines += ["", "## User request", prompt]
    lines += [
        "",
        "## Design intent (extracted from the image)",
        intent_graph.model_dump_json()[:_INTENT_CHARS],
    ]
    lines += ["", "## Repository", repo_profile.model_dump_json()[:_PROFILE_CHARS]]

    if context is not None and context.chunks:
        lines += ["", "## Repository files (read-only context)"]
        for chunk in context.chunks:
            lines += [
                f"--- {chunk.path} (lines {chunk.start_line}-{chunk.end_line}) ---",
                chunk.content,
            ]

    if generated:
        needed = {path for dep in node.dependencies for path in by_node.get(dep, [])}
        lines += ["", "## Already generated in this run"]
        for path in needed:
            lines += [
                f"--- {path} (full content: this node depends on it) ---",
                generated[path].content,
            ]
        others = [p for p in generated if p not in needed]
        if others:
            lines.append("Other generated files: " + ", ".join(others))
    return "\n".join(lines)


def _describe_dependency(
    node_id: str, by_node: dict[str, list[str]], nodes: dict[str, GenerationNode]
) -> str:
    paths = by_node.get(node_id) or [nodes[node_id].target_path if node_id in nodes else "?"]
    return f"{node_id} ({', '.join(paths)})"


# ---------------------------------------------------------------------------
# Answer parsing
# ---------------------------------------------------------------------------


def _usable_files(answer: str, node_id: str, repo_root: Path | None) -> list[GeneratedFile]:
    produced: list[GeneratedFile] = []
    for raw_path, content in _read_answer(answer):
        path = _clean_path(raw_path)
        if path is None or not content.strip():
            logger.warning("Node %s: skipped file %r from the model answer", node_id, raw_path)
            continue
        try:
            existing = _existing(repo_root, path)
        except (OSError, ValueError):
            logger.warning("Node %s: refused unsafe or unreadable original %r", node_id, path)
            continue
        produced.append(
            GeneratedFile(
                path=path,
                content=content,
                language=language_of(path),
                source_node_id=node_id,
                is_new=existing is None,
                original_content=existing,
            )
        )
    try:
        ensure_distinct_paths([generated.path for generated in produced])
    except UnsafeRepositoryPathError as exc:
        raise GenerationError(f"Node {node_id}: model file paths collide") from exc
    return produced


def _read_answer(answer: str) -> list[tuple[str, str]]:
    blocks = parse_file_blocks(answer)
    if blocks:
        return blocks
    try:
        data: Any = parse_llm_json(answer)
    except Exception:  # noqa: BLE001
        return []
    entries: object = cast(dict[str, object], data).get("files") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return []
    pairs: list[tuple[str, str]] = []
    for entry in cast(list[object], entries):
        if not isinstance(entry, dict):
            continue
        item = cast(dict[str, object], entry)
        path, content = item.get("path"), item.get("content")
        if isinstance(path, str) and isinstance(content, str):
            pairs.append((path, content))
    return pairs


def _clean_path(raw: str) -> str | None:
    try:
        path = normalize_change_path(raw)
    except UnsafeRepositoryPathError:
        return None
    return path


def _existing(repo_root: Path | None, path: str) -> str | None:
    if repo_root is None:
        return None
    try:
        return read_source(repo_root, path).decode("utf-8")[:_ORIGINAL_CHARS]
    except FileNotFoundError:
        return None

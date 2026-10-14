"""CodeGenerator hands the model the design and the repo, and refuses to hide failures."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.exceptions import GenerationError
from ddk.models.context_pack import ContextChunk, ContextPack
from ddk.models.generation import GenerationNode, GenerationPlan
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile
from ddk.services.code_generator import CodeGenerator

IMAGE = [("QUJD", "image/png")]


class ScriptedLLM:
    """Answers each call from a queue and keeps the calls."""

    def __init__(self, *answers: str | LLMResponse) -> None:
        self._answers = list(answers)
        self.calls: list[tuple[list[Message], LLMCallConfig]] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self.calls.append((messages, config))
        answer = self._answers.pop(0)
        if isinstance(answer, LLMResponse):
            return answer
        return LLMResponse(content=answer, model=config.model)

    async def complete_structured(
        self, messages: list[Message], config: LLMCallConfig, output_schema: type
    ) -> LLMResponse:
        return await self.complete(messages, config)


def _plan(*nodes: tuple[str, str, str, list[str]]) -> GenerationPlan:
    return GenerationPlan(
        case_id="C-001",
        nodes=[
            GenerationNode(id=i, node_type=t, target_path=p, dependencies=d)  # type: ignore[arg-type]
            for i, t, p, d in nodes
        ],
        execution_order=[n[0] for n in nodes],
    )


def _intent() -> IntentGraph:
    return IntentGraph(
        id="C-001",
        source_image_hash="h",
        layout_regions=[],
        components=[],
        interactions=[],
        confidence=0.9,
    )


def _files(*pairs: tuple[str, str]) -> str:
    return "\n".join(f"=== FILE: {path} ===\n{content}" for path, content in pairs)


async def _generate(llm: ScriptedLLM, plan: GenerationPlan, **kwargs: Any) -> Any:
    return await CodeGenerator(llm).generate_all(
        plan, RepoProfile(framework="react"), _intent(), "make a card", **kwargs
    )


class TestFileBlocks:
    async def test_blocks_become_files_with_language_from_the_suffix(self) -> None:
        answer = _files(
            ("src/Card.tsx", "export const Card = () => <div/>;\n"),
            ("src/Card.css", ".card { color: red; }\n"),
        )
        llm = ScriptedLLM(answer)

        result = await _generate(llm, _plan(("n1", "component", "src/Card.tsx", [])))

        assert [(f.path, f.language) for f in result.files] == [
            ("src/Card.tsx", "typescript"),
            ("src/Card.css", "css"),
        ]
        assert result.file_map["src/Card.css"] == ".card { color: red; }\n"
        assert result.generation_trace == ["n1:src/Card.tsx"]

    async def test_fences_around_a_block_are_removed(self) -> None:
        llm = ScriptedLLM("=== FILE: src/a.ts ===\n```ts\nexport const a = 1;\n```\n")

        result = await _generate(llm, _plan(("n1", "file", "src/a.ts", [])))

        assert result.files[0].content == "export const a = 1;\n"

    async def test_json_answers_are_still_understood(self) -> None:
        answer = json.dumps({"files": [{"path": "src/a.ts", "content": "export const a = 1;"}]})

        result = await _generate(ScriptedLLM(answer), _plan(("n1", "file", "src/a.ts", [])))

        assert result.file_map == {"src/a.ts": "export const a = 1;"}


class TestFailuresAreLoud:
    @pytest.mark.parametrize("answer", ["", "I cannot help with that.", "{not json"])
    async def test_answer_without_files_is_an_error_naming_the_node(self, answer: str) -> None:
        with pytest.raises(GenerationError, match="n1"):
            await _generate(ScriptedLLM(answer), _plan(("n1", "file", "src/a.ts", [])))

    async def test_truncated_answer_is_an_error_with_the_reason(self) -> None:
        cut = LLMResponse(
            content=_files(("src/a.ts", "export const a = ")), model="m", truncated=True
        )

        with pytest.raises(GenerationError, match="cut off"):
            await _generate(ScriptedLLM(cut), _plan(("n1", "file", "src/a.ts", [])))

    @pytest.mark.parametrize(
        "path", ["/etc/passwd", "../outside.ts", "package.json", ".env", "pnpm-lock.yaml"]
    )
    async def test_paths_outside_the_source_tree_are_refused(self, path: str) -> None:
        llm = ScriptedLLM(_files((path, "x")))

        with pytest.raises(GenerationError, match="no usable file"):
            await _generate(llm, _plan(("n1", "file", "src/a.ts", [])))

    async def test_one_bad_path_does_not_drop_the_good_files(self) -> None:
        llm = ScriptedLLM(_files(("package.json", "{}"), ("src/a.ts", "export const a = 1;\n")))

        result = await _generate(llm, _plan(("n1", "file", "src/a.ts", [])))

        assert list(result.file_map) == ["src/a.ts"]


class TestWhatTheModelSees:
    async def test_design_images_go_with_every_node_call(self) -> None:
        llm = ScriptedLLM(_files(("src/a.ts", "a")), _files(("src/b.ts", "b")))
        plan = _plan(("n1", "file", "src/a.ts", []), ("n2", "file", "src/b.ts", ["n1"]))

        await _generate(llm, plan, images=IMAGE)

        assert [m[-1].images for m, _ in llm.calls] == [IMAGE, IMAGE]

    async def test_no_images_means_no_image_blocks(self) -> None:
        llm = ScriptedLLM(_files(("src/a.ts", "a")))

        await _generate(llm, _plan(("n1", "file", "src/a.ts", [])))

        assert llm.calls[0][0][-1].images is None

    async def test_files_from_earlier_nodes_are_shown_in_full_when_depended_on(self) -> None:
        llm = ScriptedLLM(
            _files(("src/types.ts", "export interface Props { title: string }\n")),
            _files(("src/Card.tsx", "x")),
            _files(("src/other.ts", "y")),
        )
        plan = _plan(
            ("n1", "type", "src/types.ts", []),
            ("n2", "component", "src/Card.tsx", ["n1"]),
            ("n3", "file", "src/other.ts", []),
        )

        await _generate(llm, plan)

        card_prompt = llm.calls[1][0][-1].content
        assert "export interface Props { title: string }" in card_prompt
        other_prompt = llm.calls[2][0][-1].content
        assert "export interface Props" not in other_prompt
        assert "src/types.ts" in other_prompt  # path only: the file exists, import it by name

    async def test_repo_context_is_included(self) -> None:
        pack = ContextPack(
            node_name="generate",
            target_files=["src/Card.tsx"],
            chunks=[
                ContextChunk(
                    path="src/App.tsx",
                    priority="P1",
                    start_line=1,
                    end_line=3,
                    content="export default function App() { return null }",
                    content_sha256="0" * 64,
                )
            ],
            total_lines=3,
            context_pack_hash="abc",
        )
        llm = ScriptedLLM(_files(("src/Card.tsx", "x")))

        await _generate(llm, _plan(("n1", "component", "src/Card.tsx", [])), context=pack)

        prompt = llm.calls[0][0][-1].content
        assert "src/App.tsx" in prompt and "export default function App()" in prompt

    async def test_prompt_states_the_node_and_the_users_request(self) -> None:
        llm = ScriptedLLM(_files(("src/Card.tsx", "x")))

        await _generate(llm, _plan(("n1", "component", "src/Card.tsx", [])))

        messages, config = llm.calls[0]
        assert messages[0].content.startswith("Generate")
        user = messages[-1].content
        assert "src/Card.tsx" in user and "make a card" in user
        assert config.max_tokens >= 8192
        assert config.metadata["purpose"] == "generate"

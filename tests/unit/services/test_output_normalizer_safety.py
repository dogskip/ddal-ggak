"""OutputNormalizer never lets a bad model answer damage or silently drop generated files."""

from __future__ import annotations

import json

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.repo import RepoProfile
from ddk.services.output_normalizer import OutputNormalizer

_CARD = 'export const Card = () => {\n  return <div className="card">Hello world</div>;\n};\n' * 4


class ScriptedLLM:
    def __init__(self, content: str, *, truncated: bool = False) -> None:
        self.content = content
        self.truncated = truncated
        self.configs: list[LLMCallConfig] = []

    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self.configs.append(config)
        return LLMResponse(content=self.content, model=config.model, truncated=self.truncated)

    async def complete_structured(
        self, messages: list[Message], config: LLMCallConfig, output_schema: type
    ) -> LLMResponse:
        return await self.complete(messages, config)


def _artifacts() -> GeneratedArtifactSet:
    card = GeneratedFile(
        path="src/Card.tsx", content=_CARD, language="typescript", source_node_id="n1", is_new=True
    )
    return GeneratedArtifactSet(
        case_id="C-001",
        files=[card],
        file_map={card.path: card.content},
        generation_trace=["n1:src/Card.tsx"],
        total_tokens_used=321,
        changed_paths=[card.path],
        trace={"images": 1, "context_pack_hash": "abc"},
    )


def _answer(patched: dict[str, str]) -> str:
    return json.dumps({"convention_fixes": [], "unresolved_drift": [], "patched_files": patched})


async def _normalize(llm: ScriptedLLM) -> tuple[object, GeneratedArtifactSet, GeneratedArtifactSet]:
    artifacts = _artifacts()
    report, result = await OutputNormalizer(llm=llm).normalize(
        artifacts, RepoProfile(framework="react")
    )
    return report, result, artifacts


async def test_answer_cut_off_by_the_token_limit_keeps_the_files_and_says_so() -> None:
    report, result, artifacts = await _normalize(
        ScriptedLLM('{"patched_files": {"src/Ca', truncated=True)
    )

    assert result is artifacts
    assert report.skipped_rules == ["normalization-truncated"]  # type: ignore[attr-defined]


async def test_answer_that_is_not_json_keeps_the_files_and_says_so() -> None:
    report, result, artifacts = await _normalize(ScriptedLLM("sorry, I cannot do that"))

    assert result is artifacts
    assert report.skipped_rules == ["normalization-unparseable"]  # type: ignore[attr-defined]


async def test_token_limit_leaves_room_for_whole_files() -> None:
    llm = ScriptedLLM(_answer({}))

    await _normalize(llm)

    assert llm.configs[0].max_tokens >= 8192


async def test_a_sound_patch_is_applied_and_keeps_the_rest_of_the_artifact_set() -> None:
    patched_text = _CARD.replace("Hello world", "Hello, world")
    report, result, artifacts = await _normalize(
        ScriptedLLM(_answer({"src/Card.tsx": patched_text}))
    )

    assert result.file_map["src/Card.tsx"] == patched_text
    assert report.files_modified == ["src/Card.tsx"]  # type: ignore[attr-defined]
    assert report.skipped_rules == []  # type: ignore[attr-defined]
    assert result.files[0].original_content is None  # new file: nothing to compare with
    assert result.total_tokens_used == 321
    assert result.trace == {"images": 1, "context_pack_hash": "abc"}
    assert result.generation_trace == artifacts.generation_trace


async def test_patch_for_a_file_that_was_not_generated_is_ignored() -> None:
    report, result, artifacts = await _normalize(ScriptedLLM(_answer({"src/Other.tsx": "x" * 200})))

    assert result.file_map == artifacts.file_map
    assert report.skipped_rules == ["patch-rejected:src/Other.tsx:unknown-file"]  # type: ignore[attr-defined]


async def test_empty_patch_is_rejected() -> None:
    report, result, artifacts = await _normalize(ScriptedLLM(_answer({"src/Card.tsx": "  \n"})))

    assert result.file_map == artifacts.file_map
    assert report.skipped_rules == ["patch-rejected:src/Card.tsx:empty"]  # type: ignore[attr-defined]


async def test_patch_that_throws_away_half_of_the_file_is_rejected() -> None:
    report, result, artifacts = await _normalize(
        ScriptedLLM(_answer({"src/Card.tsx": _CARD[: len(_CARD) // 3]}))
    )

    assert result.file_map == artifacts.file_map
    assert report.skipped_rules == ["patch-rejected:src/Card.tsx:shrunk"]  # type: ignore[attr-defined]


async def test_patch_that_elides_code_with_a_placeholder_comment_is_rejected() -> None:
    elided = _CARD + "// ... rest of the component unchanged\n"
    report, result, artifacts = await _normalize(ScriptedLLM(_answer({"src/Card.tsx": elided})))

    assert result.file_map == artifacts.file_map
    assert report.skipped_rules == ["patch-rejected:src/Card.tsx:elided"]  # type: ignore[attr-defined]


async def test_object_spread_is_not_mistaken_for_an_elision() -> None:
    spread = _CARD + "const styles = {\n  ...base,\n  color: 'red',\n};\n"
    report, result, _ = await _normalize(ScriptedLLM(_answer({"src/Card.tsx": spread})))

    assert result.file_map["src/Card.tsx"] == spread
    assert report.skipped_rules == []  # type: ignore[attr-defined]

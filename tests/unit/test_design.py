"""Comprehensive unit tests for the ddk.design module.

Covers:
  - templates.py  : PromptTemplate dataclass, TEMPLATES dict
  - interviewer.py: _parse_interview_response, _extract_project_name,
                    InterviewResult, DesignInterviewer
  - generator.py  : GeneratedDocument, GenerationResult, DesignGenerator
  - writer.py     : DesignWriter, _write_document, _write_errors,
                    _write_manifest, _write_readme
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.design.generator import DesignGenerator, GeneratedDocument, GenerationResult
from ddk.design.interviewer import (
    DesignInterviewer,
    InterviewResult,
    _extract_project_name,
    _parse_interview_response,
)
from ddk.design.templates import TEMPLATES, PromptTemplate
from ddk.design.writer import (
    DesignWriter,
    _write_document,
    _write_errors,
    _write_manifest,
    _write_readme,
)

# ==============================================================================
# FakeLLM — reusable test double
# ==============================================================================

_EXPECTED_TEMPLATE_KEYS = [
    "00-interview-record",
    "01-srs",
    "02-prd",
    "03-architecture",
    "04-api-spec",
    "05-database-schema",
    "06-security-design",
    "07-adr-set",
    "08-test-strategy",
    "09-implementation-plan",
    "10-ai-handoff",
]


class FakeLLM:
    """Sequential response fake.  Returns responses in order; replays the last
    response if the call index exceeds the list length.  Implements LLMAdapter
    duck-type (complete + complete_structured)."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses: list[str] = responses or ["default response"]
        self._idx: int = 0
        self.call_log: list[tuple[list[Message], LLMCallConfig]] = []

    async def complete(
        self,
        messages: list[Message],
        config: LLMCallConfig,
    ) -> LLMResponse:
        self.call_log.append((messages, config))
        content = self._responses[min(self._idx, len(self._responses) - 1)]
        self._idx += 1
        return LLMResponse(
            content=content,
            model=config.model,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
        )

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,  # noqa: ARG002
    ) -> LLMResponse:
        return await self.complete(messages, config)


class AlwaysFailLLM:
    """LLM double that always raises RuntimeError."""

    async def complete(
        self,
        messages: list[Message],
        config: LLMCallConfig,
    ) -> LLMResponse:
        raise RuntimeError("API unavailable")

    async def complete_structured(
        self,
        messages: list[Message],
        config: LLMCallConfig,
        output_schema: type,
    ) -> LLMResponse:
        raise RuntimeError("API unavailable")


# ==============================================================================
# Shared fixtures
# ==============================================================================


@pytest.fixture
def simple_interview() -> InterviewResult:
    return InterviewResult(
        project_name="TaskApp",
        original_idea="Build a task management app",
        turns=[
            {"q": "Who is the target user?", "a": "Software developers"},
            {"q": "What is the core feature?", "a": "Kanban board"},
        ],
        extracted_requirements=[
            "REQ-001: User authentication",
            "REQ-002: Task creation and editing",
        ],
    )


@pytest.fixture
def two_doc_result() -> GenerationResult:
    return GenerationResult(
        documents=[
            GeneratedDocument(
                key="01-srs",
                filename="01-srs.md",
                content="# SRS\n\nContent here.",
                cost_usd=0.001,
            ),
            GeneratedDocument(
                key="02-prd",
                filename="02-prd.md",
                content="# PRD\n\nContent here.",
                cost_usd=0.002,
            ),
        ],
        total_cost_usd=0.003,
    )


# ==============================================================================
# templates.py
# ==============================================================================


class TestPromptTemplate:
    def test_is_frozen_dataclass(self) -> None:
        tmpl = PromptTemplate(system="sys", user="usr")
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            tmpl.system = "changed"  # type: ignore[misc]

    def test_equality_same_values(self) -> None:
        a = PromptTemplate(system="s", user="u")
        b = PromptTemplate(system="s", user="u")
        assert a == b

    def test_inequality_different_values(self) -> None:
        a = PromptTemplate(system="s1", user="u")
        b = PromptTemplate(system="s2", user="u")
        assert a != b

    def test_fields_accessible(self) -> None:
        tmpl = PromptTemplate(system="sys text", user="user text")
        assert tmpl.system == "sys text"
        assert tmpl.user == "user text"


class TestTemplatesDict:
    def test_count_is_eleven(self) -> None:
        assert len(TEMPLATES) == 11

    def test_all_expected_keys_present(self) -> None:
        assert list(TEMPLATES.keys()) == _EXPECTED_TEMPLATE_KEYS

    def test_keys_have_numeric_prefix(self) -> None:
        for key in TEMPLATES:
            prefix = key.split("-")[0]
            assert prefix.isdigit(), f"Key '{key}' does not start with a numeric prefix"

    def test_all_templates_are_prompt_template_instances(self) -> None:
        for key, tmpl in TEMPLATES.items():
            assert isinstance(tmpl, PromptTemplate), f"'{key}' is not a PromptTemplate"

    def test_all_system_prompts_nonempty(self) -> None:
        for key, tmpl in TEMPLATES.items():
            assert tmpl.system.strip(), f"'{key}' has empty system prompt"

    def test_all_user_prompts_nonempty(self) -> None:
        for key, tmpl in TEMPLATES.items():
            assert tmpl.user.strip(), f"'{key}' has empty user prompt"

    def test_first_template_key(self) -> None:
        assert "00-interview-record" in TEMPLATES

    def test_last_template_key(self) -> None:
        assert "10-ai-handoff" in TEMPLATES

    def test_api_spec_template_mentions_yaml(self) -> None:
        """04-api-spec should request YAML output."""
        assert "yaml" in TEMPLATES["04-api-spec"].user.lower()

    def test_user_prompts_contain_format_placeholders(self) -> None:
        """Every user template must reference {project_name}."""
        for key, tmpl in TEMPLATES.items():
            assert "{project_name}" in tmpl.user, f"'{key}' user prompt missing {{project_name}}"

    def test_templates_immutable_after_creation(self) -> None:
        """TEMPLATES dict values must be frozen; adding a key creates a copy."""
        original_count = len(TEMPLATES)
        # Verify we can't accidentally mutate the PromptTemplate
        tmpl = TEMPLATES["01-srs"]
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            tmpl.user = "hacked"  # type: ignore[misc]
        assert len(TEMPLATES) == original_count


# ==============================================================================
# interviewer.py — _parse_interview_response
# ==============================================================================


class TestParseInterviewResponse:
    def test_valid_json_parsed_correctly(self) -> None:
        content = json.dumps(
            {"question": "What is your goal?", "done": False, "extracted": ["req-1"]}
        )
        result = _parse_interview_response(content)
        assert result["question"] == "What is your goal?"
        assert result["done"] is False
        assert result["extracted"] == ["req-1"]

    def test_code_block_with_language_tag(self) -> None:
        inner = json.dumps({"question": "Target user?", "done": False, "extracted": []})
        content = f"```json\n{inner}\n```"
        result = _parse_interview_response(content)
        assert result["question"] == "Target user?"
        assert result["done"] is False

    def test_code_block_without_language_tag(self) -> None:
        inner = json.dumps({"question": "Core feature?", "done": True, "extracted": []})
        content = f"```\n{inner}\n```"
        result = _parse_interview_response(content)
        assert result["done"] is True

    def test_invalid_json_returns_fallback(self) -> None:
        content = "This is not JSON at all."
        result = _parse_interview_response(content)
        assert result["question"] == "This is not JSON at all."
        assert result["done"] is False
        assert result["extracted"] == []

    def test_invalid_json_in_code_block_returns_fallback(self) -> None:
        content = "```\nnot valid json\n```"
        result = _parse_interview_response(content)
        # After stripping the code block, "not valid json" is invalid JSON
        assert result["done"] is False
        assert result["extracted"] == []

    def test_done_true_in_response(self) -> None:
        content = json.dumps({"question": None, "done": True, "extracted": []})
        result = _parse_interview_response(content)
        assert result["done"] is True
        assert result["question"] is None

    def test_extracted_requirements_preserved(self) -> None:
        content = json.dumps(
            {
                "question": "Q?",
                "done": False,
                "extracted": ["REQ-001: Login", "REQ-002: Logout"],
            }
        )
        result = _parse_interview_response(content)
        assert result["extracted"] == ["REQ-001: Login", "REQ-002: Logout"]

    def test_whitespace_stripped_before_parsing(self) -> None:
        content = '  \n  {"question": "Q?", "done": false, "extracted": []}  \n  '
        result = _parse_interview_response(content)
        assert result["question"] == "Q?"

    def test_empty_string_fallback(self) -> None:
        result = _parse_interview_response("")
        assert result["done"] is False
        assert result["extracted"] == []


# ==============================================================================
# interviewer.py — _extract_project_name
# ==============================================================================


class TestExtractProjectName:
    def test_short_idea_returned_unchanged(self) -> None:
        idea = "Build a todo app"
        assert _extract_project_name(idea) == idea

    def test_exactly_30_chars_returned_unchanged(self) -> None:
        idea = "A" * 30
        result = _extract_project_name(idea)
        assert result == idea
        assert "..." not in result

    def test_31_chars_truncated_with_ellipsis(self) -> None:
        idea = "A" * 31
        result = _extract_project_name(idea)
        assert result == "A" * 30 + "..."
        assert len(result) == 33

    def test_long_idea_truncated(self) -> None:
        idea = "This is a very long project idea that exceeds thirty characters"
        result = _extract_project_name(idea)
        assert result == idea[:30] + "..."

    def test_empty_string(self) -> None:
        result = _extract_project_name("")
        assert result == ""
        assert "..." not in result

    def test_exactly_29_chars_no_truncation(self) -> None:
        idea = "B" * 29
        assert _extract_project_name(idea) == idea


# ==============================================================================
# interviewer.py — InterviewResult
# ==============================================================================


class TestInterviewResult:
    def test_transcript_empty_turns(self) -> None:
        result = InterviewResult(project_name="P", original_idea="idea")
        assert result.transcript == ""

    def test_transcript_single_turn_format(self) -> None:
        result = InterviewResult(
            project_name="P",
            original_idea="idea",
            turns=[{"q": "What do you want?", "a": "A fast app"}],
        )
        transcript = result.transcript
        assert "Q1: What do you want?" in transcript
        assert "A1: A fast app" in transcript

    def test_transcript_multiple_turns_numbered(self) -> None:
        result = InterviewResult(
            project_name="P",
            original_idea="idea",
            turns=[
                {"q": "First question?", "a": "First answer"},
                {"q": "Second question?", "a": "Second answer"},
            ],
        )
        transcript = result.transcript
        assert "Q1: First question?" in transcript
        assert "A1: First answer" in transcript
        assert "Q2: Second question?" in transcript
        assert "A2: Second answer" in transcript

    def test_transcript_turns_are_numbered_sequentially(self) -> None:
        turns = [{"q": f"Q{i}?", "a": f"A{i}"} for i in range(1, 4)]
        result = InterviewResult(project_name="P", original_idea="idea", turns=turns)
        for i in range(1, 4):
            assert f"Q{i}: Q{i}?" in result.transcript
            assert f"A{i}: A{i}" in result.transcript

    def test_summary_contains_original_idea(self) -> None:
        result = InterviewResult(project_name="P", original_idea="Build a CRM system")
        assert "Build a CRM system" in result.summary

    def test_summary_contains_requirements(self) -> None:
        result = InterviewResult(
            project_name="P",
            original_idea="idea",
            extracted_requirements=["REQ-001: Login", "REQ-002: Dashboard"],
        )
        summary = result.summary
        assert "- REQ-001: Login" in summary
        assert "- REQ-002: Dashboard" in summary

    def test_summary_contains_transcript(self) -> None:
        result = InterviewResult(
            project_name="P",
            original_idea="idea",
            turns=[{"q": "Core feature?", "a": "Chat functionality"}],
        )
        summary = result.summary
        assert "Q1: Core feature?" in summary
        assert "A1: Chat functionality" in summary

    def test_summary_empty_requirements(self) -> None:
        result = InterviewResult(project_name="P", original_idea="idea")
        summary = result.summary
        assert "도출된 요구사항:" in summary

    def test_default_turns_is_empty_list(self) -> None:
        result = InterviewResult(project_name="P", original_idea="idea")
        assert result.turns == []

    def test_default_requirements_is_empty_list(self) -> None:
        result = InterviewResult(project_name="P", original_idea="idea")
        assert result.extracted_requirements == []


# ==============================================================================
# interviewer.py — DesignInterviewer.run
# ==============================================================================


class TestDesignInterviewer:
    async def test_run_produces_turns_and_requirements(self) -> None:
        responses = [
            json.dumps({"question": "Target user?", "done": False, "extracted": ["req-1"]}),
            json.dumps({"question": "Core feature?", "done": False, "extracted": ["req-2"]}),
            json.dumps({"question": None, "done": True, "extracted": ["req-3"]}),
        ]
        llm = FakeLLM(responses)
        interviewer = DesignInterviewer(llm)
        answers = iter(["Developers", "Code generation"])

        result = await interviewer.run("Make a code gen tool", lambda q: next(answers))

        assert len(result.turns) == 2
        assert result.turns[0] == {"q": "Target user?", "a": "Developers"}
        assert result.turns[1] == {"q": "Core feature?", "a": "Code generation"}
        assert result.extracted_requirements == ["req-1", "req-2", "req-3"]

    async def test_run_stops_when_done_immediately(self) -> None:
        """If first LLM response has done=True, no turns are created."""
        llm = FakeLLM(
            [json.dumps({"question": None, "done": True, "extracted": ["req-from-idea"]})]
        )
        interviewer = DesignInterviewer(llm)
        called: list[str] = []

        result = await interviewer.run("Quick idea", lambda q: called.append(q) or "answer")

        assert len(result.turns) == 0
        assert called == []
        assert "req-from-idea" in result.extracted_requirements

    async def test_run_respects_max_turns_limit(self) -> None:
        """With max_turns=3 and LLM never done, we get exactly 3 turns."""
        never_done = json.dumps({"question": "Always a question?", "done": False, "extracted": []})
        llm = FakeLLM([never_done] * 20)
        interviewer = DesignInterviewer(llm)

        result = await interviewer.run("Test idea", lambda q: "answer", max_turns=3)

        assert len(result.turns) == 3

    async def test_run_sets_project_name_from_short_idea(self) -> None:
        llm = FakeLLM([json.dumps({"question": None, "done": True, "extracted": []})])
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run("Short idea", lambda q: "x")

        assert result.project_name == "Short idea"

    async def test_run_sets_project_name_truncated_from_long_idea(self) -> None:
        long_idea = "This is a very long project idea description exceeding thirty chars"
        llm = FakeLLM([json.dumps({"question": None, "done": True, "extracted": []})])
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run(long_idea, lambda q: "x")

        assert result.project_name == long_idea[:30] + "..."

    async def test_run_preserves_original_idea(self) -> None:
        llm = FakeLLM([json.dumps({"question": None, "done": True, "extracted": []})])
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run("My original idea", lambda q: "x")

        assert result.original_idea == "My original idea"

    async def test_run_collects_requirements_across_turns(self) -> None:
        responses = [
            json.dumps({"question": "Q1?", "done": False, "extracted": ["r1", "r2"]}),
            json.dumps({"question": "Q2?", "done": False, "extracted": ["r3"]}),
            json.dumps({"question": None, "done": True, "extracted": ["r4", "r5"]}),
        ]
        llm = FakeLLM(responses)
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run("Idea", lambda q: "ans", max_turns=5)

        assert result.extracted_requirements == ["r1", "r2", "r3", "r4", "r5"]

    async def test_run_with_invalid_json_response_uses_fallback(self) -> None:
        """LLM returns non-JSON; fallback treats it as a question string."""
        llm = FakeLLM(["Plain text question here", "plain text again"])
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run("Test idea", lambda q: "answer", max_turns=2)

        # fallback: question = content, done = False → turns are created
        assert len(result.turns) == 2

    async def test_run_coerces_non_string_extracted_items(self) -> None:
        """Extracted items that are non-str non-None should be str()-coerced."""
        responses = [
            # 42 is an int, not a str — exercises the elif branch in _run
            json.dumps({"question": None, "done": True, "extracted": [42, "real-req"]}),
        ]
        llm = FakeLLM(responses)
        interviewer = DesignInterviewer(llm)
        result = await interviewer.run("Idea", lambda q: "x")

        assert "42" in result.extracted_requirements
        assert "real-req" in result.extracted_requirements

    async def test_run_llm_called_with_system_message(self) -> None:
        llm = FakeLLM([json.dumps({"question": None, "done": True, "extracted": []})])
        interviewer = DesignInterviewer(llm, model="claude-3-opus")
        await interviewer.run("Idea", lambda q: "x")

        first_call_messages, first_call_config = llm.call_log[0]
        assert any(m.role == "system" for m in first_call_messages)
        assert first_call_config.model == "claude-3-opus"


# ==============================================================================
# generator.py — dataclasses
# ==============================================================================


class TestGeneratedDocument:
    def test_creation_with_all_fields(self) -> None:
        doc = GeneratedDocument(
            key="01-srs",
            filename="01-srs.md",
            content="# SRS",
            cost_usd=0.005,
        )
        assert doc.key == "01-srs"
        assert doc.filename == "01-srs.md"
        assert doc.content == "# SRS"
        assert doc.cost_usd == pytest.approx(0.005)

    def test_default_cost_is_zero(self) -> None:
        doc = GeneratedDocument(key="k", filename="f.md", content="c")
        assert doc.cost_usd == 0.0

    def test_equality(self) -> None:
        a = GeneratedDocument(key="k", filename="f.md", content="c", cost_usd=0.1)
        b = GeneratedDocument(key="k", filename="f.md", content="c", cost_usd=0.1)
        assert a == b


class TestGenerationResult:
    def test_default_empty_documents(self) -> None:
        result = GenerationResult()
        assert result.documents == []

    def test_default_zero_cost(self) -> None:
        result = GenerationResult()
        assert result.total_cost_usd == 0.0

    def test_default_empty_errors(self) -> None:
        result = GenerationResult()
        assert result.errors == {}

    def test_with_documents(self) -> None:
        docs = [GeneratedDocument(key="01-srs", filename="01-srs.md", content="x")]
        result = GenerationResult(documents=docs, total_cost_usd=0.01)
        assert len(result.documents) == 1
        assert result.total_cost_usd == pytest.approx(0.01)

    def test_with_errors(self) -> None:
        result = GenerationResult(errors={"01-srs": "timeout"})
        assert result.errors["01-srs"] == "timeout"


# ==============================================================================
# generator.py — DesignGenerator._generate_document
# ==============================================================================


class TestDesignGeneratorDocument:
    async def test_md_extension_for_non_api_templates(
        self, simple_interview: InterviewResult
    ) -> None:
        for key in _EXPECTED_TEMPLATE_KEYS:
            if key == "04-api-spec":
                continue
            llm = FakeLLM(["# content"])
            gen = DesignGenerator(llm)
            doc = await gen._generate_document(key, simple_interview)
            assert doc.filename == f"{key}.md", f"'{key}' should produce .md"

    async def test_yaml_extension_for_api_spec(self, simple_interview: InterviewResult) -> None:
        llm = FakeLLM(["openapi: 3.0.3"])
        gen = DesignGenerator(llm)
        doc = await gen._generate_document("04-api-spec", simple_interview)
        assert doc.filename == "04-api-spec.yaml"

    async def test_content_comes_from_llm(self, simple_interview: InterviewResult) -> None:
        llm = FakeLLM(["# My Generated SRS Document\n\nContent."])
        gen = DesignGenerator(llm)
        doc = await gen._generate_document("01-srs", simple_interview)
        assert doc.content == "# My Generated SRS Document\n\nContent."

    async def test_cost_propagated_from_llm_response(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"])
        gen = DesignGenerator(llm)
        doc = await gen._generate_document("02-prd", simple_interview)
        assert doc.cost_usd == pytest.approx(0.001)

    async def test_key_set_correctly(self, simple_interview: InterviewResult) -> None:
        llm = FakeLLM(["# doc"])
        gen = DesignGenerator(llm)
        doc = await gen._generate_document("03-architecture", simple_interview)
        assert doc.key == "03-architecture"

    async def test_llm_called_with_system_and_user_messages(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"])
        gen = DesignGenerator(llm, model="claude-opus")
        await gen._generate_document("01-srs", simple_interview)

        assert len(llm.call_log) == 1
        messages, config = llm.call_log[0]
        roles = [m.role for m in messages]
        assert roles == ["system", "user"]
        assert config.model == "claude-opus"

    async def test_project_name_interpolated_in_user_message(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"])
        gen = DesignGenerator(llm)
        await gen._generate_document("01-srs", simple_interview)

        messages, _ = llm.call_log[0]
        user_content = next(m.content for m in messages if m.role == "user")
        assert simple_interview.project_name in user_content


# ==============================================================================
# generator.py — DesignGenerator.generate_all
# ==============================================================================


class TestDesignGeneratorAll:
    async def test_generates_all_eleven_documents(self, simple_interview: InterviewResult) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=11)
        result = await gen.generate_all(simple_interview)

        assert len(result.documents) == 11
        assert len(result.errors) == 0

    async def test_documents_sorted_in_template_order(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=11)
        result = await gen.generate_all(simple_interview)

        keys = [d.key for d in result.documents]
        assert keys == _EXPECTED_TEMPLATE_KEYS

    async def test_total_cost_accumulates(self, simple_interview: InterviewResult) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=11)
        result = await gen.generate_all(simple_interview)

        # FakeLLM returns cost_usd=0.001 per call; 11 calls = 0.011
        assert result.total_cost_usd == pytest.approx(0.011)

    async def test_progress_callback_called_for_every_template(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=3)
        calls: list[tuple[str, int, int]] = []

        await gen.generate_all(
            simple_interview,
            on_progress=lambda k, c, t: calls.append((k, c, t)),
        )

        assert len(calls) == 11
        keys_called = {k for k, _, _ in calls}
        assert keys_called == set(_EXPECTED_TEMPLATE_KEYS)

    async def test_progress_callback_receives_correct_total(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm)
        totals: list[int] = []

        await gen.generate_all(simple_interview, on_progress=lambda k, c, t: totals.append(t))

        assert all(t == 11 for t in totals)

    async def test_no_progress_callback_does_not_raise(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm)
        result = await gen.generate_all(simple_interview)

        assert len(result.documents) == 11

    async def test_all_errors_when_llm_always_fails(
        self, simple_interview: InterviewResult
    ) -> None:
        gen = DesignGenerator(AlwaysFailLLM())
        result = await gen.generate_all(simple_interview)

        assert len(result.documents) == 0
        assert len(result.errors) == 11
        assert set(result.errors.keys()) == set(_EXPECTED_TEMPLATE_KEYS)

    async def test_error_messages_captured(self, simple_interview: InterviewResult) -> None:
        gen = DesignGenerator(AlwaysFailLLM())
        result = await gen.generate_all(simple_interview)

        for msg in result.errors.values():
            assert "API unavailable" in msg

    async def test_partial_failure_total_equals_eleven(
        self, simple_interview: InterviewResult
    ) -> None:
        """Successful + failed docs always sums to 11."""

        class PartialFailLLM:
            def __init__(self) -> None:
                self._count = 0

            async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
                count = self._count
                self._count += 1
                if count >= 4:
                    raise RuntimeError("quota exceeded")
                return LLMResponse(content="# doc", model=config.model, cost_usd=0.001)

            async def complete_structured(
                self, messages: list[Message], config: LLMCallConfig, output_schema: type
            ) -> LLMResponse:
                return await self.complete(messages, config)

        gen = DesignGenerator(PartialFailLLM(), concurrency=1)
        result = await gen.generate_all(simple_interview)

        assert len(result.documents) + len(result.errors) == 11

    async def test_api_spec_document_has_yaml_extension(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=11)
        result = await gen.generate_all(simple_interview)

        api_doc = next(d for d in result.documents if d.key == "04-api-spec")
        assert api_doc.filename == "04-api-spec.yaml"

    async def test_non_api_spec_documents_have_md_extension(
        self, simple_interview: InterviewResult
    ) -> None:
        llm = FakeLLM(["# doc"] * 11)
        gen = DesignGenerator(llm, concurrency=11)
        result = await gen.generate_all(simple_interview)

        for doc in result.documents:
            if doc.key != "04-api-spec":
                assert doc.filename.endswith(".md"), f"'{doc.key}' should end with .md"


# ==============================================================================
# writer.py — _write_document
# ==============================================================================


class TestWriteDocumentHelper:
    def test_creates_file_with_correct_content(self, tmp_path: Path) -> None:
        doc = GeneratedDocument(key="01-srs", filename="01-srs.md", content="# SRS\n\nHello.")
        _write_document(tmp_path, doc)
        assert (tmp_path / "01-srs.md").read_text(encoding="utf-8") == "# SRS\n\nHello."

    def test_filename_used_as_path(self, tmp_path: Path) -> None:
        doc = GeneratedDocument(
            key="04-api-spec",
            filename="04-api-spec.yaml",
            content="openapi: 3.0.3",
        )
        _write_document(tmp_path, doc)
        assert (tmp_path / "04-api-spec.yaml").exists()
        assert not (tmp_path / "04-api-spec.md").exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        (tmp_path / "01-srs.md").write_text("old content")
        doc = GeneratedDocument(key="01-srs", filename="01-srs.md", content="new content")
        _write_document(tmp_path, doc)
        assert (tmp_path / "01-srs.md").read_text() == "new content"

    def test_writes_utf8_content(self, tmp_path: Path) -> None:
        doc = GeneratedDocument(key="k", filename="k.md", content="한글 텍스트 🎉")
        _write_document(tmp_path, doc)
        assert (tmp_path / "k.md").read_text(encoding="utf-8") == "한글 텍스트 🎉"


# ==============================================================================
# writer.py — _write_errors
# ==============================================================================


class TestWriteErrorsHelper:
    def test_creates_errors_md_file(self, tmp_path: Path) -> None:
        _write_errors(tmp_path, {"01-srs": "LLM timeout"})
        assert (tmp_path / "ERRORS.md").exists()

    def test_errors_md_contains_key(self, tmp_path: Path) -> None:
        _write_errors(tmp_path, {"01-srs": "LLM timeout"})
        content = (tmp_path / "ERRORS.md").read_text(encoding="utf-8")
        assert "01-srs" in content

    def test_errors_md_contains_message(self, tmp_path: Path) -> None:
        _write_errors(tmp_path, {"01-srs": "LLM timeout"})
        content = (tmp_path / "ERRORS.md").read_text(encoding="utf-8")
        assert "LLM timeout" in content

    def test_multiple_errors_all_present(self, tmp_path: Path) -> None:
        errors = {
            "01-srs": "timeout",
            "02-prd": "JSON parse error",
            "03-architecture": "rate limit",
        }
        _write_errors(tmp_path, errors)
        content = (tmp_path / "ERRORS.md").read_text(encoding="utf-8")
        for key, msg in errors.items():
            assert key in content
            assert msg in content

    def test_errors_md_has_header(self, tmp_path: Path) -> None:
        _write_errors(tmp_path, {"x": "y"})
        content = (tmp_path / "ERRORS.md").read_text(encoding="utf-8")
        assert "# " in content  # Has a heading


# ==============================================================================
# writer.py — _write_manifest
# ==============================================================================


class TestWriteManifestHelper:
    def test_creates_manifest_json(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        assert (tmp_path / "manifest.json").exists()

    def test_returns_manifest_path(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        returned = _write_manifest(tmp_path, two_doc_result, simple_interview)
        assert returned == tmp_path / "manifest.json"

    def test_manifest_schema_version_is_1_0(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["schema_version"] == "1.0"

    def test_manifest_project_name(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["project_name"] == "TaskApp"

    def test_manifest_original_idea(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["original_idea"] == "Build a task management app"

    def test_manifest_total_cost(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["total_cost_usd"] == pytest.approx(0.003)

    def test_manifest_documents_list(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert len(manifest["documents"]) == 2
        keys = [d["key"] for d in manifest["documents"]]
        assert "01-srs" in keys
        assert "02-prd" in keys

    def test_manifest_document_entry_has_required_fields(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        for entry in manifest["documents"]:
            assert "key" in entry
            assert "filename" in entry
            assert "cost_usd" in entry

    def test_manifest_requirements(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["requirements"] == simple_interview.extracted_requirements

    def test_manifest_errors_field(self, tmp_path: Path, simple_interview: InterviewResult) -> None:
        result = GenerationResult(errors={"01-srs": "failed"})
        _write_manifest(tmp_path, result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert manifest["errors"] == {"01-srs": "failed"}

    def test_manifest_generated_at_present(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_manifest(tmp_path, two_doc_result, simple_interview)
        manifest = json.loads((tmp_path / "manifest.json").read_text())
        assert "generated_at" in manifest
        assert manifest["generated_at"]  # non-empty

    def test_manifest_valid_json_encoding(
        self, tmp_path: Path, simple_interview: InterviewResult
    ) -> None:
        interview = InterviewResult(project_name="한글 프로젝트", original_idea="한국어 아이디어")
        result = GenerationResult()
        _write_manifest(tmp_path, result, interview)
        raw = (tmp_path / "manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(raw)
        assert manifest["project_name"] == "한글 프로젝트"


# ==============================================================================
# writer.py — _write_readme
# ==============================================================================


class TestWriteReadmeHelper:
    def test_creates_readme_md(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        assert (tmp_path / "README.md").exists()

    def test_readme_contains_project_name(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "TaskApp" in content

    def test_readme_contains_original_idea(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "Build a task management app" in content

    def test_readme_contains_document_links(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "[01-srs.md](01-srs.md)" in content
        assert "[02-prd.md](02-prd.md)" in content

    def test_readme_no_error_section_when_no_errors(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "Generation Errors" not in content

    def test_readme_has_error_section_when_errors(
        self, tmp_path: Path, simple_interview: InterviewResult
    ) -> None:
        result = GenerationResult(errors={"03-architecture": "LLM timeout"})
        _write_readme(tmp_path, result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert "Generation Errors" in content
        assert "03-architecture" in content

    def test_readme_has_markdown_heading(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        _write_readme(tmp_path, two_doc_result, simple_interview)
        content = (tmp_path / "README.md").read_text(encoding="utf-8")
        assert content.startswith("#")


# ==============================================================================
# writer.py — DesignWriter
# ==============================================================================


class TestDesignWriter:
    def test_write_creates_design_package_dir(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert pkg_dir.is_dir()
        assert pkg_dir.name == "design-package"

    def test_write_returns_design_package_path(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        returned = writer.write(two_doc_result, simple_interview)
        assert returned == tmp_path / "design-package"

    def test_write_creates_document_files(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert (pkg_dir / "01-srs.md").exists()
        assert (pkg_dir / "02-prd.md").exists()

    def test_write_creates_manifest_json(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert (pkg_dir / "manifest.json").exists()

    def test_write_creates_readme_md(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert (pkg_dir / "README.md").exists()

    def test_write_no_errors_md_when_no_errors(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert not (pkg_dir / "ERRORS.md").exists()

    def test_write_creates_errors_md_when_errors_present(
        self, tmp_path: Path, simple_interview: InterviewResult
    ) -> None:
        result = GenerationResult(errors={"01-srs": "LLM timeout"})
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(result, simple_interview)
        assert (pkg_dir / "ERRORS.md").exists()

    def test_write_document_content_is_correct(
        self, tmp_path: Path, simple_interview: InterviewResult
    ) -> None:
        result = GenerationResult(
            documents=[
                GeneratedDocument(
                    key="01-srs",
                    filename="01-srs.md",
                    content="# SRS\n\nDetailed requirements here.",
                )
            ]
        )
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(result, simple_interview)
        assert (pkg_dir / "01-srs.md").read_text() == "# SRS\n\nDetailed requirements here."

    def test_write_creates_parent_dirs(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        nested_output = tmp_path / "a" / "b" / "c"
        writer = DesignWriter(nested_output)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert pkg_dir.is_dir()

    def test_write_manifest_contains_correct_project_name(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(tmp_path)
        pkg_dir = writer.write(two_doc_result, simple_interview)
        manifest = json.loads((pkg_dir / "manifest.json").read_text())
        assert manifest["project_name"] == "TaskApp"

    def test_document_count_returns_correct_count(self, two_doc_result: GenerationResult) -> None:
        writer = DesignWriter("/unused")
        assert writer.document_count(two_doc_result) == 2

    def test_document_count_empty_result(self) -> None:
        writer = DesignWriter("/unused")
        assert writer.document_count(GenerationResult()) == 0

    def test_document_count_single(self) -> None:
        result = GenerationResult(
            documents=[GeneratedDocument(key="k", filename="k.md", content="")]
        )
        writer = DesignWriter("/unused")
        assert writer.document_count(result) == 1

    def test_write_accepts_string_path(
        self, tmp_path: Path, simple_interview: InterviewResult, two_doc_result: GenerationResult
    ) -> None:
        writer = DesignWriter(str(tmp_path))
        pkg_dir = writer.write(two_doc_result, simple_interview)
        assert pkg_dir.is_dir()

"""RecordingLLMAdapter keeps an audit trail of every model call; ReplayLLMAdapter plays it back."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ddk.adapters.llm.base import LLMCallConfig, LLMResponse, Message
from ddk.adapters.llm.recording import (
    CassetteMissError,
    RecordingLLMAdapter,
    ReplayLLMAdapter,
)
from tests.fakes.fake_llm_adapter import FakeLLMAdapter


def _messages(system: str = "Autofix a file", user: str = "fix it") -> list[Message]:
    return [Message(role="system", content=system), Message(role="user", content=user)]


class _Failing:
    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        raise RuntimeError("upstream exploded")

    async def complete_structured(
        self, messages: list[Message], config: LLMCallConfig, output_schema: type
    ) -> LLMResponse:
        raise RuntimeError("upstream exploded")


class TestRecording:
    async def test_response_is_passed_through_unchanged(self) -> None:
        inner = FakeLLMAdapter(responses={"autofix": "fixed"})
        recorder = RecordingLLMAdapter(inner)

        response = await recorder.complete(_messages(), LLMCallConfig(model="m-1"))

        assert response.content == "fixed"

    async def test_every_call_is_recorded_with_cost_and_tokens(self) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"autofix": "x", "analyze": "{}"}))

        await recorder.complete(_messages(), LLMCallConfig(model="m-1"))
        await recorder.complete_structured(
            _messages("Analyze a screenshot"), LLMCallConfig(model="m-2"), dict
        )

        assert [r.purpose for r in recorder.records] == ["autofix", "analyze"]
        assert [r.model for r in recorder.records] == ["m-1", "m-2"]
        assert recorder.records[0].input_tokens == 100
        assert recorder.records[0].output_tokens == 50
        assert recorder.total_cost_usd == pytest.approx(0.002)
        assert [r.sequence for r in recorder.records] == [1, 2]

    async def test_failed_call_is_recorded_and_raised(self) -> None:
        recorder = RecordingLLMAdapter(_Failing())

        with pytest.raises(RuntimeError, match="upstream exploded"):
            await recorder.complete(_messages(), LLMCallConfig(model="m-1"))

        assert recorder.records[0].status == "error"
        assert recorder.records[0].error == "RuntimeError"
        assert recorder.total_cost_usd == 0.0

    async def test_purpose_can_be_set_explicitly(self) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"autofix": "x"}))
        config = LLMCallConfig(model="m", metadata={"purpose": "repair"})

        await recorder.complete(_messages(), config)

        assert recorder.records[0].purpose == "repair"

    async def test_request_digest_follows_the_content_and_images(self) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"autofix": "x", "default": "x"}))
        config = LLMCallConfig(model="m")
        with_image = [Message(role="user", content="same", images=[("QUJD", "image/png")])]
        other_image = [Message(role="user", content="same", images=[("REVG", "image/png")])]
        system = _messages()

        await recorder.complete(system, config)
        await recorder.complete(system, config)
        await recorder.complete(with_image, config)
        await recorder.complete(other_image, config)

        digests = [r.request_digest for r in recorder.records]
        assert digests[0] == digests[1]
        assert len({digests[0], digests[2], digests[3]}) == 3

    async def test_effort_changes_the_request_digest_but_unset_effort_keeps_the_old_one(
        self,
    ) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"autofix": "x"}))

        await recorder.complete(_messages(), LLMCallConfig(model="m"))
        await recorder.complete(_messages(), LLMCallConfig(model="m", effort="low"))
        await recorder.complete(_messages(), LLMCallConfig(model="m", effort="high"))

        plain, low, high = (r.request_digest for r in recorder.records)
        assert len({plain, low, high}) == 3
        earlier = json.dumps(
            [[["system", "Autofix a file", []], ["user", "fix it", []]], "m", 0.0, 4096],
            ensure_ascii=False,
        )
        assert plain == hashlib.sha256(earlier.encode()).hexdigest()[:16]

    async def test_image_bytes_are_never_stored_in_the_record(self) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"default": "x"}))
        secret = "QUJDREVGR0hJSktMTU5PUA=="

        await recorder.complete(
            [Message(role="user", content="look", images=[(secret, "image/png")])],
            LLMCallConfig(model="m"),
        )

        assert secret not in recorder.records[0].model_dump_json()

    async def test_references_and_export_are_json_ready(self) -> None:
        recorder = RecordingLLMAdapter(FakeLLMAdapter(responses={"autofix": "x"}))
        await recorder.complete(_messages(), LLMCallConfig(model="m"))

        assert recorder.references("C-001") == ["llm-call:C-001:1"]
        assert json.loads(json.dumps(recorder.export()))[0]["purpose"] == "autofix"


class TestCassette:
    async def test_recorded_session_replays_without_the_inner_adapter(self, tmp_path: Path) -> None:
        cassette = tmp_path / "session.json"
        recorder = RecordingLLMAdapter(
            FakeLLMAdapter(responses={"autofix": "first", "analyze": "second"}),
            cassette_path=cassette,
        )
        await recorder.complete(_messages(), LLMCallConfig(model="m"))
        await recorder.complete_structured(_messages("Analyze UI"), LLMCallConfig(model="m"), dict)
        recorder.save()

        replay = ReplayLLMAdapter.load(cassette)
        first = await replay.complete(_messages(user="different text"), LLMCallConfig(model="m"))
        second = await replay.complete_structured(
            _messages("Analyze UI"), LLMCallConfig(model="m"), dict
        )

        assert (first.content, second.content) == ("first", "second")
        assert first.cost_usd == 0.0

    async def test_same_purpose_is_replayed_in_order(self, tmp_path: Path) -> None:
        cassette = tmp_path / "session.json"
        inner = FakeLLMAdapter(responses={"autofix": "one"})
        recorder = RecordingLLMAdapter(inner, cassette_path=cassette)
        await recorder.complete(_messages(), LLMCallConfig(model="m"))
        inner.responses["autofix"] = "two"
        await recorder.complete(_messages(), LLMCallConfig(model="m"))
        recorder.save()

        replay = ReplayLLMAdapter.load(cassette)

        contents = [
            (await replay.complete(_messages(), LLMCallConfig(model="m"))).content for _ in range(2)
        ]
        assert contents == ["one", "two"]

    async def test_missing_recording_is_a_clear_error(self, tmp_path: Path) -> None:
        cassette = tmp_path / "session.json"
        cassette.write_text(json.dumps({"version": 1, "calls": []}))

        with pytest.raises(CassetteMissError, match="autofix"):
            await ReplayLLMAdapter.load(cassette).complete(_messages(), LLMCallConfig(model="m"))

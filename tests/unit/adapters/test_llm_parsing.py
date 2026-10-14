"""Tests for robust LLM JSON parsing (fence/prose tolerance)."""

from __future__ import annotations

import pytest

from ddk.adapters.llm.parsing import parse_llm_json, strip_code_fences
from ddk.exceptions import LLMResponseError


class TestStripCodeFences:
    def test_plain_text_unchanged(self) -> None:
        assert strip_code_fences('{"a": 1}') == '{"a": 1}'

    def test_json_fence_removed(self) -> None:
        assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'

    def test_bare_fence_removed(self) -> None:
        assert strip_code_fences('```\n{"a": 1}\n```') == '{"a": 1}'


class TestParseLLMJson:
    def test_plain_json(self) -> None:
        assert parse_llm_json('{"a": 1}') == {"a": 1}

    def test_json_fenced(self) -> None:
        assert parse_llm_json('```json\n{"a": 1, "b": [2, 3]}\n```') == {"a": 1, "b": [2, 3]}

    def test_leading_prose(self) -> None:
        assert parse_llm_json('Here is the result:\n{"ok": true}') == {"ok": True}

    def test_trailing_prose(self) -> None:
        assert parse_llm_json('{"ok": true}\n\nLet me know if you need changes.') == {"ok": True}

    def test_array_payload(self) -> None:
        assert parse_llm_json("[1, 2, 3]") == [1, 2, 3]

    def test_braces_inside_strings_not_miscounted(self) -> None:
        text = '{"code": "function f() { return {a: 1}; }"}'
        assert parse_llm_json(text) == {"code": "function f() { return {a: 1}; }"}

    def test_fenced_with_prose_around(self) -> None:
        text = 'Sure!\n```json\n{"files": []}\n```\nDone.'
        assert parse_llm_json(text) == {"files": []}

    def test_garbage_raises(self) -> None:
        with pytest.raises(LLMResponseError):
            parse_llm_json("this is not json at all")

    def test_empty_raises(self) -> None:
        with pytest.raises(LLMResponseError):
            parse_llm_json("")

    def test_unbalanced_braces_raises(self) -> None:
        with pytest.raises(LLMResponseError):
            parse_llm_json('{"a": 1')

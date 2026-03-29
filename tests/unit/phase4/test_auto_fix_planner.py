"""Wave 3 — AutoFixPlanner: 11 unit tests (TDD Red → Green)."""

from __future__ import annotations

import pytest

from ddk.models.validation import FailureRecord
from ddk.services.auto_fix_planner import (
    AutoFixPlanner,
    r01_remove_unused_import,
    r02_eslint_fix_command,
    r03_add_any_annotation,
    r04_add_cast,
    r05_add_dependency,
    r06_fix_relative_import,
    r07_add_optional_chaining,
    r08_add_await,
)
from tests.fakes.fake_llm_adapter import FakeLLMAdapter


# ──────────────────────────────────────────────
# Deterministic rule functions
# ──────────────────────────────────────────────


class TestDeterministicRules:
    def test_r01_removes_unused_import_line(self) -> None:
        content = "import { Foo } from './Foo';\nimport { Bar } from './Bar';\n"
        result = r01_remove_unused_import(content, "Foo")
        assert "Foo" not in result
        assert "Bar" in result

    def test_r02_returns_eslint_fix_command(self) -> None:
        cmd = r02_eslint_fix_command("src/App.tsx")
        assert "eslint" in cmd
        assert "--fix" in cmd
        assert "src/App.tsx" in cmd

    def test_r03_adds_any_annotation_to_param(self) -> None:
        content = "function foo(bar) { return bar; }"
        result = r03_add_any_annotation(content, "bar")
        assert "bar: any" in result

    def test_r04_inserts_unknown_cast(self) -> None:
        content = "const x = someValue;"
        result = r04_add_cast(content, "someValue", "MyType")
        assert "as unknown as MyType" in result

    def test_r05_adds_missing_dependency_to_package_json(self) -> None:
        pkg_json = '{"dependencies": {}}'
        result = r05_add_dependency(pkg_json, "lodash", "^4.17.21")
        assert '"lodash"' in result
        assert "^4.17.21" in result

    def test_r06_rewrites_relative_import_path(self) -> None:
        content = "import Foo from '../wrong/path';"
        result = r06_fix_relative_import(content, "../wrong/path", "../correct/path")
        assert "../correct/path" in result
        assert "../wrong/path" not in result

    def test_r07_adds_optional_chaining(self) -> None:
        content = "const name = user.profile.name;"
        result = r07_add_optional_chaining(content, "user.profile.name")
        assert "user?.profile?.name" in result

    def test_r08_adds_await_keyword(self) -> None:
        content = "const data = fetchData();"
        result = r08_add_await(content, "fetchData()")
        assert "await fetchData()" in result


# ──────────────────────────────────────────────
# AutoFixPlanner — LLM + dispatch
# ──────────────────────────────────────────────


class TestAutoFixPlannerLLM:
    async def test_r09_calls_llm_with_autofix_key(self) -> None:
        fake_llm = FakeLLMAdapter(
            responses={
                "autofix": "// fixed\nexport default function App() { return <div/>; }"
            }
        )
        planner = AutoFixPlanner(llm=fake_llm)
        failure = FailureRecord(
            id="f1",
            taxonomy_id="FT-BUILD-002",
            severity="critical",
            message="SyntaxError: Unexpected token",
            raw_output="SyntaxError",
        )
        attempt, _ = await planner.plan_and_apply(
            failures=[failure],
            artifacts=None,
            case_id="test-case",
            attempt_number=1,
        )
        assert len(fake_llm.call_log) == 1
        assert fake_llm.call_log[0]["key"] == "autofix"
        assert attempt.rule_id == "R-09"


class TestNoApplicableRule:
    async def test_no_applicable_rule_returns_empty_patches(self) -> None:
        fake_llm = FakeLLMAdapter(responses={})
        planner = AutoFixPlanner(llm=fake_llm)
        failure = FailureRecord(
            id="f2",
            taxonomy_id="FT-UNKNOWN",
            severity="major",
            message="something weird",
            raw_output="something",
        )
        attempt, _ = await planner.plan_and_apply(
            failures=[failure],
            artifacts=None,
            case_id="test-case",
            attempt_number=1,
        )
        assert attempt.files_patched == []
        assert attempt.rule_id == "none"


class TestTaxonomyDispatch:
    async def test_applies_rule_matching_taxonomy_id(self) -> None:
        fake_llm = FakeLLMAdapter(responses={})
        planner = AutoFixPlanner(llm=fake_llm)
        failure = FailureRecord(
            id="f3",
            taxonomy_id="FT-LINT-001",
            severity="minor",
            message="Unused variable 'Foo'",
            raw_output="",
            file_path="src/App.tsx",
        )
        attempt, _ = await planner.plan_and_apply(
            failures=[failure],
            artifacts=None,
            case_id="test-case",
            attempt_number=1,
        )
        assert attempt.rule_id == "R-01"

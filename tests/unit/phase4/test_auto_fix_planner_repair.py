"""AutoFixPlanner repairs from real diagnostics and reports only what it actually changed."""

from __future__ import annotations

from pathlib import Path

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.validation import FailureRecord
from ddk.services.auto_fix_planner import AutoFixPlanner, r01_remove_unused_import
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

APP = """import { useState, useEffect } from 'react';

export default function App() {
  useEffect(() => {}, []);
  const count: number = 'x';
  return <h1>{count}</h1>;
}
"""


def _artifacts(files: dict[str, str]) -> GeneratedArtifactSet:
    return GeneratedArtifactSet(
        case_id="C-001",
        files=[
            GeneratedFile(path=p, content=c, language="typescript", source_node_id="n")
            for p, c in files.items()
        ],
    )


def _failure(
    message: str,
    *,
    taxonomy_id: str = "FT-TYPE-001",
    file_path: str | None = "src/App.tsx",
    line: int | None = 5,
    code: str | None = "TS2322",
) -> FailureRecord:
    return FailureRecord(
        id=f"f-{abs(hash((message, file_path, line))) % 10_000}",
        taxonomy_id=taxonomy_id,
        severity="major",
        message=message,
        file_path=file_path,
        line_number=line,
        code=code,
        raw_output=f"{file_path}:{line} {message}",
    )


def _content(artifacts: GeneratedArtifactSet, path: str) -> str:
    return next(f.content for f in artifacts.files if f.path == path)


class TestUnusedImports:
    def test_only_the_unused_specifier_is_removed(self) -> None:
        content = "import { useState, useEffect } from 'react';\nuseEffect(() => {});\n"

        assert r01_remove_unused_import(content, "useState") == (
            "import { useEffect } from 'react';\nuseEffect(() => {});\n"
        )

    def test_a_default_import_keeps_the_named_ones(self) -> None:
        content = "import React, { useState } from 'react';\nuseState(0);\n"

        assert r01_remove_unused_import(content, "React") == (
            "import { useState } from 'react';\nuseState(0);\n"
        )

    def test_alias_is_matched_by_its_local_name(self) -> None:
        content = "import { a as b, c } from './m';\nc();\n"

        assert r01_remove_unused_import(content, "b") == "import { c } from './m';\nc();\n"

    def test_import_that_becomes_empty_is_dropped(self) -> None:
        content = "import { Foo } from './Foo';\nimport { Bar } from './Bar';\n"

        assert r01_remove_unused_import(content, "Foo") == "import { Bar } from './Bar';\n"

    def test_type_only_import_is_handled(self) -> None:
        content = "import type { Props } from './types';\nexport {};\n"

        assert r01_remove_unused_import(content, "Props") == "export {};\n"

    def test_multi_line_import_is_left_for_the_model(self) -> None:
        content = "import {\n  a,\n  b,\n} from './m';\n"

        assert r01_remove_unused_import(content, "a") == content

    async def test_planner_applies_it_without_calling_the_model(self) -> None:
        llm = FakeLLMAdapter()
        failure = _failure(
            "'useState' is declared but its value is never read. (TS6133)",
            taxonomy_id="FT-LINT-001",
            code="TS6133",
            line=1,
        )

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [failure], _artifacts({"src/App.tsx": APP}), "C-001", 1
        )

        assert llm.call_log == []
        assert attempt.rule_id == "R-01"
        assert attempt.success is True
        assert attempt.files_patched == ["src/App.tsx"]
        assert "import { useEffect } from 'react';" in _content(patched, "src/App.tsx")


class TestWrongRelativeImport:
    FAILURE = "Cannot find module './Button' or its corresponding type declarations. (TS2307)"

    def _failure(self) -> FailureRecord:
        return _failure(self.FAILURE, taxonomy_id="FT-BUILD-001", code="TS2307", line=1)

    async def test_import_is_pointed_at_the_generated_file_that_matches(self) -> None:
        llm = FakeLLMAdapter()
        artifacts = _artifacts(
            {
                "src/App.tsx": "import { Button } from './Button';\nexport default Button;\n",
                "src/components/Button.tsx": "export const Button = () => null;\n",
            }
        )

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [self._failure()], artifacts, "C-001", 1
        )

        assert llm.call_log == []
        assert attempt.rule_id == "R-06"
        assert "from './components/Button'" in _content(patched, "src/App.tsx")

    async def test_ambiguous_match_is_left_to_the_model(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "export default 1;\n"})
        artifacts = _artifacts(
            {
                "src/App.tsx": "import { Button } from './Button';\nexport default Button;\n",
                "src/a/Button.tsx": "export const Button = () => null;\n",
                "src/b/Button.tsx": "export const Button = () => null;\n",
            }
        )

        attempt, _ = await AutoFixPlanner(llm).plan_and_apply(
            [self._failure()], artifacts, "C-001", 1
        )

        assert len(llm.call_log) == 1
        assert attempt.rule_id == "R-09"


class TestModelRepair:
    async def test_all_diagnostics_of_a_file_go_into_one_call(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("'x'", "1")})
        failures = [
            _failure("Type 'string' is not assignable to type 'number'.", line=5),
            _failure("Argument of type 'X' is not assignable.", code="TS2345", line=6),
        ]

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            failures, _artifacts({"src/App.tsx": APP}), "C-001", 1
        )

        assert len(llm.call_log) == 1
        prompt = llm.call_log[0]["messages"][1].content
        assert "line 5" in prompt and "TS2322" in prompt
        assert "line 6" in prompt and "TS2345" in prompt
        assert "5 | " in prompt  # numbered source so the model can find the lines
        assert attempt.rule_id == "R-09"
        assert attempt.success is True
        assert "const count: number = 1;" in _content(patched, "src/App.tsx")
        assert len(attempt.trigger_failures) == 2

    async def test_type_errors_are_repaired_not_silenced_by_regex(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("'x'", "1")})

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": APP}),
            "C-001",
            1,
        )

        assert attempt.rule_id == "R-09"
        assert "as unknown as" not in _content(patched, "src/App.tsx")

    async def test_markdown_fences_around_the_answer_are_removed(self) -> None:
        fixed = APP.replace("'x'", "1")
        llm = FakeLLMAdapter(responses={"autofix": f"```tsx\n{fixed}```\n"})

        _, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": APP}),
            "C-001",
            1,
        )

        assert _content(patched, "src/App.tsx") == fixed

    async def test_unchanged_answer_is_not_reported_as_success(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP})

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": APP}),
            "C-001",
            1,
        )

        assert attempt.success is False
        assert attempt.files_patched == []
        assert _content(patched, "src/App.tsx") == APP

    async def test_answer_that_silences_the_checker_is_rejected(self) -> None:
        silenced = APP.replace("const count", "// @ts-ignore\n  const count")
        llm = FakeLLMAdapter(responses={"autofix": silenced})

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": APP}),
            "C-001",
            1,
        )

        assert attempt.success is False
        assert "rejected" in attempt.patch_description
        assert _content(patched, "src/App.tsx") == APP

    async def test_new_any_annotations_are_rejected(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("number", "any")})

        attempt, _ = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": APP}),
            "C-001",
            1,
        )

        assert attempt.success is False

    async def test_truncated_answer_is_rejected(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "export default function App() {"})
        long_file = APP + "// padding\n" * 40

        attempt, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("Type 'string' is not assignable to type 'number'.")],
            _artifacts({"src/App.tsx": long_file}),
            "C-001",
            1,
        )

        assert attempt.success is False
        assert _content(patched, "src/App.tsx") == long_file

    async def test_error_in_a_consumer_file_is_repaired_through_the_generated_file(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "export default function App() {}\n"})
        consumer_error = _failure(
            "Module './App' has no default export.",
            file_path="src/main.tsx",
            line=3,
            code="TS1192",
        )

        attempt, _ = await AutoFixPlanner(llm).plan_and_apply(
            [consumer_error],
            _artifacts({"src/App.tsx": "export function App() {}\n"}),
            "C-001",
            1,
        )

        prompt = llm.call_log[0]["messages"][1].content
        assert "src/main.tsx" in prompt
        assert "has no default export" in prompt
        assert attempt.files_patched == ["src/App.tsx"]

    async def test_at_most_four_files_are_repaired_per_attempt(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "export const fixed = 1;\n"})
        files = {f"src/f{i}.ts": f"export const v{i}: number = 'x';\n" for i in range(6)}
        failures = [
            _failure("Type 'string' is not assignable to type 'number'.", file_path=path, line=1)
            for path in files
        ]

        attempt, _ = await AutoFixPlanner(llm).plan_and_apply(
            failures, _artifacts(files), "C-001", 1
        )

        assert len(llm.call_log) == 4
        assert len(attempt.trigger_failures) == 4
        assert len(attempt.remaining_failures) == 2


class TestAdditionalFiles:
    ANSWER = (
        "import { Button } from './Button';\nexport default Button;\n"
        "=== FILE: src/Button.tsx ===\nexport const Button = () => null;\n"
    )

    async def test_missing_module_can_be_created_when_the_repo_lacks_it(
        self, tmp_path: Path
    ) -> None:
        llm = FakeLLMAdapter(responses={"autofix": self.ANSWER})
        planner = AutoFixPlanner(llm, repo_root=tmp_path)

        attempt, patched = await planner.plan_and_apply(
            [_failure("Cannot find module './Button'.", taxonomy_id="FT-BUILD-001", line=1)],
            _artifacts({"src/App.tsx": "import { Button } from './Button';\n"}),
            "C-001",
            1,
        )

        assert _content(patched, "src/Button.tsx") == "export const Button = () => null;\n"
        assert set(attempt.files_patched) == {"src/App.tsx", "src/Button.tsx"}
        assert next(f for f in patched.files if f.path == "src/Button.tsx").is_new is True

    async def test_existing_repo_file_is_never_overwritten(self, tmp_path: Path) -> None:
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "Button.tsx").write_text("// owned by the user\n")
        llm = FakeLLMAdapter(responses={"autofix": self.ANSWER})

        _, patched = await AutoFixPlanner(llm, repo_root=tmp_path).plan_and_apply(
            [_failure("Cannot find module './Button'.", taxonomy_id="FT-BUILD-001", line=1)],
            _artifacts({"src/App.tsx": "import { Button } from './Button';\n"}),
            "C-001",
            1,
        )

        assert "src/Button.tsx" not in {f.path for f in patched.files}

    async def test_dependency_and_config_files_are_off_limits(self, tmp_path: Path) -> None:
        answer = (
            "export default 1;\n"
            "=== FILE: package.json ===\n{}\n"
            "=== FILE: tsconfig.json ===\n{}\n"
            "=== FILE: .env ===\nSECRET=1\n"
            "=== FILE: ../escape.ts ===\nexport {};\n"
        )
        llm = FakeLLMAdapter(responses={"autofix": answer})

        _, patched = await AutoFixPlanner(llm, repo_root=tmp_path).plan_and_apply(
            [_failure("Cannot find module './x'.", taxonomy_id="FT-BUILD-001", line=1)],
            _artifacts({"src/App.tsx": "import x from './x';\n"}),
            "C-001",
            1,
        )

        assert {f.path for f in patched.files} == {"src/App.tsx"}


class TestHonestReporting:
    async def test_no_failures_means_no_patch(self) -> None:
        attempt, _ = await AutoFixPlanner(FakeLLMAdapter()).plan_and_apply(
            [], _artifacts({"src/App.tsx": APP}), "C-001", 1
        )

        assert attempt.rule_id == "none"
        assert attempt.success is False

    async def test_nothing_to_patch_costs_no_model_call(self) -> None:
        llm = FakeLLMAdapter()

        attempt, _ = await AutoFixPlanner(llm).plan_and_apply(
            [_failure("boom", taxonomy_id="FT-BUILD-002", file_path=None, line=None)],
            None,
            "C-001",
            1,
        )

        assert llm.call_log == []
        assert attempt.rule_id == "none"
        assert attempt.success is False
        assert attempt.files_patched == []
        assert "no generated file" in attempt.patch_description.lower()


class TestArtifactSetStaysConsistent:
    TYPE_ERROR = "Type 'string' is not assignable to type 'number'."

    def _set(self) -> GeneratedArtifactSet:
        return GeneratedArtifactSet(
            case_id="C-001",
            files=[GeneratedFile(path="src/App.tsx", content=APP, source_node_id="n")],
            file_map={"src/App.tsx": APP},
            changed_paths=["src/App.tsx"],
            total_tokens_used=7,
            trace={"images": 1},
        )

    async def test_file_map_follows_the_patched_file_and_the_rest_is_kept(self) -> None:
        fixed = APP.replace("'x'", "1")
        llm = FakeLLMAdapter(responses={"autofix": fixed})

        _, patched = await AutoFixPlanner(llm).plan_and_apply(
            [_failure(self.TYPE_ERROR)], self._set(), "C-001", 1
        )

        assert patched.file_map == {"src/App.tsx": fixed}
        assert patched.total_tokens_used == 7
        assert patched.trace == {"images": 1}

    async def test_a_file_added_by_the_repair_is_listed_everywhere(self, tmp_path: Path) -> None:
        fixed = APP.replace("'x'", "1")
        llm = FakeLLMAdapter(
            responses={"autofix": f"{fixed}\n=== FILE: src/extra.ts ===\nexport const x = 1;\n"}
        )

        _, patched = await AutoFixPlanner(llm, repo_root=tmp_path).plan_and_apply(
            [_failure(self.TYPE_ERROR)], self._set(), "C-001", 1
        )

        assert patched.file_map["src/extra.ts"] == "export const x = 1;\n"
        assert patched.changed_paths == ["src/App.tsx", "src/extra.ts"]

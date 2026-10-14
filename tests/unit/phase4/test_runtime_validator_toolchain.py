"""RuntimeValidator against real tool output: where diagnostics land, what counts as a failure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ddk.adapters.sandbox.base import CommandResult
from ddk.services.runtime_validator import RuntimeValidator
from tests.fakes import (
    FakePlaywrightAdapter,
    FakeSSIMAdapter,
    ProjectSandbox,
    ScriptedBuildRunner,
)

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "diagnostics"

BUILD = "npm run build"
TSC_APP = "npm exec --no -- tsc --noEmit -p tsconfig.app.json"
ESLINT = "npm exec --no -- eslint ."
INSTALL = "npm ci --ignore-scripts --no-audit --no-fund"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _vite_project(*, installed: bool = True) -> dict[str, str]:
    files = {
        "package.json": json.dumps(
            {
                "name": "app",
                "scripts": {"build": "tsc -b && vite build"},
                "dependencies": {"react": "^19"},
                "devDependencies": {"typescript": "^5", "eslint": "^9"},
            }
        ),
        "package-lock.json": "{}",
        "tsconfig.json": json.dumps({"files": [], "references": [{"path": "./tsconfig.app.json"}]}),
        "tsconfig.app.json": "{}",
        "eslint.config.js": "export default []",
    }
    if installed:
        files["node_modules/.bin/.keep"] = ""
    return files


def _validator(
    runner: ScriptedBuildRunner,
    files: dict[str, str] | None = None,
    **options: Any,
) -> RuntimeValidator:
    return RuntimeValidator(
        sandbox=ProjectSandbox(_vite_project() if files is None else files),
        build_runner=runner,
        playwright=FakePlaywrightAdapter(),
        screenshot_diff=FakeSSIMAdapter(),
        **options,
    )


def _state() -> dict[str, Any]:
    return {"case_id": "C-001", "generated_artifacts": None}


def _failed(stdout: str = "", stderr: str = "", code: int = 1) -> CommandResult:
    return CommandResult(returncode=code, stdout=stdout, stderr=stderr, duration_ms=5)


class TestDiagnosticsReachTheReport:
    async def test_tsc_errors_printed_on_stdout_become_located_failures(self) -> None:
        runner = ScriptedBuildRunner({BUILD: _failed(stdout=_fixture("tsc_plain.txt"))})

        report, _ = await _validator(runner).run(_state())

        assert report.build_success is False
        mismatch = next(f for f in report.failures if f.code == "TS2322")
        assert (mismatch.file_path, mismatch.line_number) == ("src/App.tsx", 4)
        assert mismatch.taxonomy_id == "FT-TYPE-001"
        assert mismatch.message == "Type 'string' is not assignable to type 'number'."
        assert mismatch.source == "build"
        assert len(report.failures) == 3

    async def test_error_seen_by_build_and_typecheck_is_listed_once(self) -> None:
        output = _fixture("tsc_plain.txt")
        runner = ScriptedBuildRunner(
            {BUILD: _failed(stdout=output), TSC_APP: _failed(stdout=output, code=2)}
        )

        report, _ = await _validator(runner).run(_state())

        keys = [(f.file_path, f.line_number, f.code) for f in report.failures]
        assert len(keys) == len(set(keys)) == 3
        assert report.type_check_success is False

    async def test_eslint_errors_become_lint_failures_with_rule_as_code(self) -> None:
        runner = ScriptedBuildRunner({ESLINT: _failed(stdout=_fixture("eslint_stylish.txt"))})

        report, _ = await _validator(runner).run(_state())

        assert report.lint_success is False
        assert {f.code for f in report.failures} == {"@typescript-eslint/no-unused-vars"}
        assert all(f.source == "lint" and f.taxonomy_id == "FT-LINT-001" for f in report.failures)

    async def test_bundler_error_on_stderr_is_captured_too(self) -> None:
        runner = ScriptedBuildRunner({BUILD: _failed(stderr=_fixture("vite_esbuild_syntax.txt"))})

        report, _ = await _validator(runner).run(_state())

        assert [(f.file_path, f.line_number) for f in report.failures] == [("src/App.tsx", 3)]

    async def test_unparseable_failure_keeps_the_raw_output(self) -> None:
        runner = ScriptedBuildRunner({BUILD: _failed(stdout="kaboom: something odd happened")})

        report, _ = await _validator(runner).run(_state())

        assert len(report.failures) == 1
        assert "kaboom" in report.failures[0].raw_output
        assert report.failures[0].source == "build"

    async def test_warning_only_output_with_a_zero_exit_is_not_a_failure(self) -> None:
        warning = "/work/app/src/A.tsx\n  2:5  warning  Unexpected console statement  no-console\n"
        runner = ScriptedBuildRunner(
            {ESLINT: CommandResult(returncode=0, stdout=warning, stderr="", duration_ms=1)}
        )

        report, _ = await _validator(runner).run(_state())

        assert report.lint_success is True
        assert report.failures == []

    async def test_failure_count_is_capped(self) -> None:
        lines = "".join(
            f"src/f{i}.ts(1,1): error TS2304: Cannot find name 'x{i}'.\n" for i in range(120)
        )
        runner = ScriptedBuildRunner({BUILD: _failed(stdout=lines)})

        report, _ = await _validator(runner).run(_state())

        assert 0 < len(report.failures) <= 50


class TestStepsAreReportedHonestly:
    async def test_every_planned_step_is_listed_with_its_status(self) -> None:
        runner = ScriptedBuildRunner({ESLINT: _failed(stdout=_fixture("eslint_stylish.txt"))})

        report, _ = await _validator(runner).run(_state())

        assert [(s.name, s.status) for s in report.steps] == [
            ("build", "passed"),
            ("typecheck", "passed"),
            ("lint", "failed"),
        ]
        assert report.steps[2].error_count == 2

    async def test_inapplicable_steps_are_skipped_with_a_reason(self) -> None:
        files = {"package.json": json.dumps({"name": "plain", "scripts": {"build": "vite build"}})}
        runner = ScriptedBuildRunner()

        report, _ = await _validator(runner, files).run(_state())

        skipped = {s.name: s.summary for s in report.steps if s.status == "skipped"}
        assert set(skipped) == {"typecheck", "lint"}
        assert runner.commands() == [BUILD]
        assert report.type_check_success and report.lint_success

    async def test_project_without_package_json_runs_nothing(self) -> None:
        runner = ScriptedBuildRunner()

        report, _ = await _validator(runner, {}).run(_state())

        assert runner.commands() == []
        assert {s.status for s in report.steps} == {"skipped"}

    async def test_timeout_is_a_failure_of_the_step(self) -> None:
        runner = ScriptedBuildRunner(
            {BUILD: _failed(stderr="Command timed out after 300s", code=124)}
        )

        report, _ = await _validator(runner).run(_state())

        assert report.steps[0].status == "failed"
        assert report.build_success is False
        assert any("timed out" in f.message for f in report.failures)

    async def test_step_timeout_is_passed_to_the_runner(self) -> None:
        runner = ScriptedBuildRunner()

        await _validator(runner, step_timeout_s=42).run(_state())

        assert {entry["timeout"] for entry in runner.run_log} == {42}


class TestMissingToolchain:
    async def test_uninstalled_dependencies_are_an_environment_problem_not_code(self) -> None:
        runner = ScriptedBuildRunner()

        report, _ = await _validator(runner, _vite_project(installed=False)).run(_state())

        assert runner.commands() == []
        assert {s.status for s in report.steps} == {"unavailable"}
        assert report.failures == []
        assert report.build_success is False
        assert any("install" in issue for issue in report.environment_issues)

    async def test_install_option_installs_before_the_checks(self) -> None:
        runner = ScriptedBuildRunner()

        report, _ = await _validator(
            runner, _vite_project(installed=False), install_dependencies=True
        ).run(_state())

        assert runner.commands()[0] == INSTALL
        assert runner.commands()[1:] == [BUILD, TSC_APP, ESLINT]
        assert report.steps[0].name == "install"
        assert report.steps[0].status == "passed"
        assert report.build_success is True

    async def test_failed_install_makes_the_checks_unavailable(self) -> None:
        runner = ScriptedBuildRunner(
            {INSTALL: _failed(stderr="npm error code ENOTFOUND registry.npmjs.org")}
        )

        report, _ = await _validator(
            runner, _vite_project(installed=False), install_dependencies=True
        ).run(_state())

        assert runner.commands() == [INSTALL]
        assert report.steps[0].status == "failed"
        assert {s.status for s in report.steps[1:]} == {"unavailable"}
        assert report.failures == []
        assert any("ENOTFOUND" in issue for issue in report.environment_issues)

    async def test_missing_local_tool_is_unavailable_not_a_code_failure(self) -> None:
        missing = "npm error npx canceled due to missing packages and no YES option"
        runner = ScriptedBuildRunner({ESLINT: _failed(stderr=missing)})

        report, _ = await _validator(runner).run(_state())

        lint = next(s for s in report.steps if s.name == "lint")
        assert lint.status == "unavailable"
        assert report.failures == []
        assert report.lint_success is False

    async def test_command_not_found_exit_codes_are_unavailable(self) -> None:
        runner = ScriptedBuildRunner({BUILD: _failed(stderr="Command not found: npm", code=127)})

        report, _ = await _validator(runner).run(_state())

        assert report.steps[0].status == "unavailable"
        assert report.failures == []

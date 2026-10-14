"""Diagnostics parser tests; fixtures are real output from a Vite + React + TS app."""

from __future__ import annotations

from pathlib import Path

from ddk.services.diagnostics import Diagnostic, parse_diagnostics, strip_ansi

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "diagnostics"
ROOT = Path("/work/app")


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _by_code(diagnostics: list[Diagnostic]) -> dict[str, Diagnostic]:
    return {f"{d.code}@{d.line}": d for d in diagnostics}


class TestTypeScript:
    def test_plain_format_extracts_location_code_and_message(self) -> None:
        diagnostics = parse_diagnostics(_read("tsc_plain.txt"), root=ROOT)

        found = _by_code(diagnostics)["TS2322@4"]
        assert found.file_path == "src/App.tsx"
        assert (found.line, found.column) == (4, 9)
        assert found.message == "Type 'string' is not assignable to type 'number'."
        assert found.severity == "error"

    def test_every_diagnostic_line_is_returned(self) -> None:
        diagnostics = parse_diagnostics(_read("tsc_plain.txt"), root=ROOT)

        assert [d.code for d in diagnostics] == ["TS6133", "TS2322", "TS6133"]

    def test_npm_run_build_banner_is_ignored(self) -> None:
        diagnostics = parse_diagnostics(_read("npm_build_tsc_error.txt"), root=ROOT)

        assert [(d.code, d.file_path, d.line) for d in diagnostics] == [
            ("TS2307", "src/App.tsx", 1)
        ]

    def test_pretty_format_with_ansi_colors(self) -> None:
        raw = _read("tsc_pretty_ansi.txt")
        assert "\x1b[" in raw

        diagnostics = parse_diagnostics(raw, root=ROOT)

        assert [(d.code, d.file_path, d.line, d.column) for d in diagnostics] == [
            ("TS2322", "src/App.tsx", 1, 7)
        ]

    def test_continuation_lines_extend_the_previous_message(self) -> None:
        raw = (
            "src/a.ts(2,3): error TS2345: Argument of type 'X' is not assignable to parameter.\n"
            "  Type 'X' is missing the following properties from type 'Y': a, b\n"
            "src/b.ts(1,1): error TS2304: Cannot find name 'foo'.\n"
        )

        diagnostics = parse_diagnostics(raw, root=ROOT)

        assert len(diagnostics) == 2
        assert "missing the following properties" in diagnostics[0].message
        assert diagnostics[1].message == "Cannot find name 'foo'."


class TestEslint:
    def test_stylish_makes_path_relative_and_keeps_rule_as_code(self) -> None:
        diagnostics = parse_diagnostics(_read("eslint_stylish.txt"), root=ROOT)

        assert [(d.file_path, d.line, d.column, d.code) for d in diagnostics] == [
            ("src/App.tsx", 1, 10, "@typescript-eslint/no-unused-vars"),
            ("src/App.tsx", 4, 9, "@typescript-eslint/no-unused-vars"),
        ]
        assert diagnostics[0].message == "'useState' is defined but never used"

    def test_summary_line_is_not_a_diagnostic(self) -> None:
        diagnostics = parse_diagnostics(_read("eslint_stylish.txt"), root=ROOT)

        assert all("problems" not in d.message for d in diagnostics)

    def test_parsing_error_has_no_rule_code(self) -> None:
        diagnostics = parse_diagnostics(_read("eslint_parse_error.txt"), root=ROOT)

        assert len(diagnostics) == 1
        assert diagnostics[0].code is None
        assert diagnostics[0].message == "Parsing error: '>' expected"
        assert (diagnostics[0].file_path, diagnostics[0].line) == ("src/App.tsx", 3)

    def test_json_formatter_output(self) -> None:
        diagnostics = parse_diagnostics(_read("eslint.json"), root=ROOT)

        assert [(d.file_path, d.line, d.code) for d in diagnostics] == [
            ("src/App.tsx", 1, "@typescript-eslint/no-unused-vars"),
            ("src/App.tsx", 4, "@typescript-eslint/no-unused-vars"),
        ]
        assert all(d.severity == "error" for d in diagnostics)

    def test_warnings_are_kept_but_marked(self) -> None:
        raw = (
            "/work/app/src/A.tsx\n"
            "  2:5  warning  Unexpected console statement  no-console\n"
            "  9:1  error    'x' is not defined            no-undef\n"
        )

        diagnostics = parse_diagnostics(raw, root=ROOT)

        assert [(d.code, d.severity) for d in diagnostics] == [
            ("no-console", "warning"),
            ("no-undef", "error"),
        ]


class TestBundlers:
    def test_rollup_unresolved_import_uses_file_line_after_error_header(self) -> None:
        diagnostics = parse_diagnostics(_read("vite_unresolved.txt"), root=ROOT)

        assert len(diagnostics) == 1
        assert diagnostics[0].file_path == "src/App.tsx"
        assert 'Could not resolve "./Button"' in diagnostics[0].message

    def test_esbuild_transform_error_has_line_and_column(self) -> None:
        diagnostics = parse_diagnostics(_read("vite_esbuild_syntax.txt"), root=ROOT)

        assert len(diagnostics) == 1
        assert (diagnostics[0].file_path, diagnostics[0].line, diagnostics[0].column) == (
            "src/App.tsx",
            3,
            0,
        )
        assert diagnostics[0].message == 'Expected ">" but found "}"'

    def test_node_stack_frames_are_not_diagnostics(self) -> None:
        diagnostics = parse_diagnostics(_read("vite_esbuild_syntax.txt"), root=ROOT)

        assert all("node_modules" not in (d.file_path or "") for d in diagnostics)


class TestPathsAndFallback:
    def test_unrecognised_output_yields_nothing(self) -> None:
        assert parse_diagnostics("npm ERR! something exploded\n", root=ROOT) == []
        assert parse_diagnostics("", root=ROOT) == []

    def test_absolute_path_outside_root_is_left_alone(self) -> None:
        raw = "/elsewhere/lib/x.ts(1,1): error TS2304: Cannot find name 'q'.\n"

        diagnostics = parse_diagnostics(raw, root=ROOT)

        assert diagnostics[0].file_path == "/elsewhere/lib/x.ts"

    def test_backslash_paths_are_normalised_to_posix(self) -> None:
        raw = "src\\ui\\Btn.tsx(2,2): error TS2304: Cannot find name 'q'.\n"

        diagnostics = parse_diagnostics(raw, root=ROOT)

        assert diagnostics[0].file_path == "src/ui/Btn.tsx"

    def test_strip_ansi_removes_color_codes_only(self) -> None:
        assert strip_ansi("\x1b[91merror\x1b[0m TS1") == "error TS1"

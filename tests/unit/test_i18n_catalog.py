"""The English table matches the messages in the source, one for one."""

from __future__ import annotations

import ast
import re
import string
from collections.abc import Iterator
from pathlib import Path

import pytest

from ddk.i18n import ENGLISH

SRC = Path(__file__).resolve().parents[2] / "src" / "ddk"
HANGUL = re.compile(r"[가-힣]")

# Modules whose output the user reads; every Korean string in them must go through ``t``.
TRANSLATED = [
    *sorted((SRC / "cli").glob("*.py")),
    SRC / "services" / "progress.py",
    SRC / "services" / "case_report.py",
    SRC / "demo" / "runner.py",
]


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _calls_to_t(path: Path) -> Iterator[ast.Call]:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t":
            yield node


def _fields(text: str) -> set[str]:
    names: set[str] = set()
    for _, field, _, _ in string.Formatter().parse(text):
        if field is not None:
            assert field != "", f"unnamed field in {text!r}"
            names.add(field)
    return names


def _messages() -> dict[str, list[tuple[Path, int, set[str]]]]:
    """Each literal passed to ``t`` with where it is used and the field names it is given."""
    found: dict[str, list[tuple[Path, int, set[str]]]] = {}
    for path in _source_files():
        for call in _calls_to_t(path):
            first = call.args[0] if call.args else None
            assert isinstance(first, ast.Constant) and isinstance(first.value, str), (
                f"{path.relative_to(SRC)}:{call.lineno}: t() needs a string literal"
            )
            given = {kw.arg for kw in call.keywords if kw.arg is not None}
            found.setdefault(first.value, []).append((path, call.lineno, given))
    return found


class TestTable:
    def test_every_message_has_an_english_entry(self) -> None:
        missing = sorted(set(_messages()) - set(ENGLISH))
        assert not missing, "no English entry for:\n" + "\n".join(missing)

    def test_every_entry_is_used(self) -> None:
        unused = sorted(set(ENGLISH) - set(_messages()))
        assert not unused, "entries no call uses:\n" + "\n".join(unused)

    def test_entries_keep_the_same_fields(self) -> None:
        for source, english in ENGLISH.items():
            assert _fields(source) == _fields(english), f"fields differ: {source!r}"

    def test_calls_give_exactly_the_fields_of_the_message(self) -> None:
        for message, uses in _messages().items():
            for path, line, given in uses:
                assert given == _fields(message), (
                    f"{path.relative_to(SRC)}:{line}: fields {sorted(given)} "
                    f"do not match {sorted(_fields(message))}"
                )

    def test_sources_are_korean_and_entries_are_english(self) -> None:
        for source, english in ENGLISH.items():
            assert HANGUL.search(source), f"source has no Korean: {source!r}"
            assert not HANGUL.search(english), f"entry still has Korean: {english!r}"

    def test_entries_do_not_just_repeat_the_source(self) -> None:
        assert [s for s, e in ENGLISH.items() if s == e] == []


class TestCoverage:
    @pytest.mark.parametrize("path", TRANSLATED, ids=lambda p: str(p.relative_to(SRC)))
    def test_no_korean_outside_t(self, path: Path) -> None:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        covered: set[int] = set()
        docstrings: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
            ):
                covered.update(id(n) for n in ast.walk(node))
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                first = node.body[0] if node.body else None
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docstrings.add(id(first.value))
        stray = [
            f"{path.relative_to(SRC)}:{node.lineno}: {node.value[:40]!r}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and HANGUL.search(node.value)
            and id(node) not in covered
            and id(node) not in docstrings
        ]
        assert not stray, "Korean text outside t():\n" + "\n".join(stray)

    @pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.relative_to(SRC)))
    def test_t_is_never_shadowed(self, path: Path) -> None:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports_t = any(
            isinstance(node, ast.ImportFrom)
            and node.module == "ddk.i18n"
            and any(alias.name == "t" and alias.asname is None for alias in node.names)
            for node in ast.walk(tree)
        )
        if not imports_t:
            return
        rebound = [
            node.lineno
            for node in ast.walk(tree)
            if (isinstance(node, ast.Name) and node.id == "t" and isinstance(node.ctx, ast.Store))
            or (isinstance(node, ast.arg) and node.arg == "t")
        ]
        assert not rebound, f"{path.relative_to(SRC)} rebinds t on lines {rebound}"

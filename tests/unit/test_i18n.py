"""Message language: the Korean source text, or its English entry."""

from __future__ import annotations

import pytest

from ddk.i18n import ENGLISH, language, t

_LOCALE_VARIABLES = ("DDK_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _LOCALE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


class TestLanguage:
    def test_english_without_any_hint(self) -> None:
        assert language() == "en"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("ko", "ko"), ("KO", "ko"), ("ko_KR.UTF-8", "ko"), ("en", "en"), ("fr", "en")],
    )
    def test_ddk_lang(self, monkeypatch: pytest.MonkeyPatch, value: str, expected: str) -> None:
        monkeypatch.setenv("DDK_LANG", value)
        assert language() == expected

    @pytest.mark.parametrize("name", ["LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"])
    def test_korean_locale_variable(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        monkeypatch.setenv(name, "ko_KR.UTF-8")
        assert language() == "ko"

    def test_other_locales_are_english(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "ja_JP.UTF-8")
        assert language() == "en"

    def test_c_locale_is_english(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "C.UTF-8")
        assert language() == "en"

    def test_ddk_lang_beats_the_locale(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANG", "ko_KR.UTF-8")
        monkeypatch.setenv("DDK_LANG", "en")
        assert language() == "en"

    def test_first_locale_variable_that_is_set_decides(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
        monkeypatch.setenv("LANG", "ko_KR.UTF-8")
        assert language() == "en"

    def test_blank_values_are_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "  ")
        monkeypatch.setenv("LANG", "ko_KR.UTF-8")
        assert language() == "ko"


class TestTranslate:
    @pytest.fixture(autouse=True)
    def _entries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(ENGLISH, "시험 문장", "test sentence")
        monkeypatch.setitem(ENGLISH, "파일 {count}개: {name}", "{count} file(s): {name}")

    def test_korean_returns_the_source_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "ko")
        assert t("시험 문장") == "시험 문장"

    def test_english_returns_the_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "en")
        assert t("시험 문장") == "test sentence"

    def test_fields_are_filled_in_both_languages(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "ko")
        assert t("파일 {count}개: {name}", count=2, name="a.tsx") == "파일 2개: a.tsx"
        monkeypatch.setenv("DDK_LANG", "en")
        assert t("파일 {count}개: {name}", count=2, name="a.tsx") == "2 file(s): a.tsx"

    def test_a_missing_entry_falls_back_to_the_source_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DDK_LANG", "en")
        assert t("번역이 없는 문장") == "번역이 없는 문장"
        assert t("번역이 없는 {x}", x=1) == "번역이 없는 1"

    def test_braces_stay_literal_without_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "ko")
        assert t('JSON 예: {"a": 1}') == 'JSON 예: {"a": 1}'

    def test_values_are_not_parsed_as_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DDK_LANG", "ko")
        assert t("파일 {count}개: {name}", count=1, name="{x}.tsx") == "파일 1개: {x}.tsx"

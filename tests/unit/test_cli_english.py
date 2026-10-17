"""The command line speaks English unless the language is Korean."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from tests.unit.test_cli_demo import _result  # pyright: ignore[reportPrivateUsage]

HANGUL = re.compile(r"[가-힣]")
ROOT = Path(__file__).resolve().parents[2]

runner = CliRunner()
ENGLISH = {"DDK_LANG": "en"}

# Every command's --help, read in a fresh process because help text is fixed at import.
_HELP_SCRIPT = """
import json, sys
from typer.main import get_command
from typer.testing import CliRunner
from ddk.cli import app

def walk(command, path):
    yield path
    for name, sub in sorted(getattr(command, "commands", {}).items()):
        yield from walk(sub, [*path, name])

root = get_command(app)
runner = CliRunner()
out = {}
for path in walk(root, []):
    out[" ".join(path) or "ddk"] = runner.invoke(app, [*path, "--help"]).output
json.dump(out, sys.stdout)
"""


def _help_pages(language: str) -> dict[str, str]:
    env = {**os.environ, "DDK_LANG": language, "PYTHONPATH": str(ROOT / "src"), "COLUMNS": "200"}
    done = subprocess.run(
        [sys.executable, "-c", _HELP_SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def english_help() -> dict[str, str]:
    return _help_pages("en")


class TestHelp:
    def test_every_command_is_listed(self, english_help: dict[str, str]) -> None:
        assert {"run", "demo", "apply", "doctor", "design new"} <= set(english_help)

    def test_english_help_has_no_korean(self, english_help: dict[str, str]) -> None:
        stray = {name: page for name, page in english_help.items() if HANGUL.search(page)}
        assert not stray, "Korean in English help:\n" + "\n".join(stray)

    def test_korean_help_is_still_korean(self) -> None:
        assert HANGUL.search(_help_pages("ko")["run"])

    def test_run_help_explains_the_prompt_is_optional(self, english_help: dict[str, str]) -> None:
        from typer.main import get_command

        command = get_command(app).commands["run"]
        prompt = next(parameter for parameter in command.params if parameter.name == "prompt")
        from ddk.i18n import ENGLISH

        help_text = ENGLISH.get(prompt.help, prompt.help)
        assert "default: implement the image as it is" in help_text


class TestMessages:
    @pytest.mark.usefixtures("no_browser_start")
    def test_doctor_readiness_labels_follow_the_selected_language(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["doctor", "--repo", str(tmp_path)], env=ENGLISH)
        assert result.exit_code in (0, 1), result.output
        assert "settings" in result.output.lower()
        assert not HANGUL.search(result.output)

    def test_unreadable_settings_name_the_variable(self) -> None:
        result = runner.invoke(app, ["run", "x.png"], env={**ENGLISH, "DDK_COST_CAP_USD": "plenty"})

        assert result.exit_code == 3
        assert "Invalid settings" in result.output
        assert "DDK_COST_CAP_USD" in result.output
        assert "got: 'plenty'" in result.output
        assert not HANGUL.search(result.output)

    def test_missing_api_key(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["run", "x.png", "--repo", str(tmp_path)],
            env={**ENGLISH, "DDK_ANTHROPIC_API_KEY": "", "ANTHROPIC_API_KEY": ""},
        )

        assert result.exit_code == 3
        assert "No Anthropic API key found" in result.output
        assert not HANGUL.search(result.output)

    def test_missing_image(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["run", "nope.png", "--repo", str(tmp_path)],
            env={**ENGLISH, "DDK_ANTHROPIC_API_KEY": "sk-ant-test"},
        )

        assert result.exit_code == 3
        assert "Design image not found" in result.output
        assert not HANGUL.search(result.output)

    def test_status_without_cases(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["status", "--repo", str(tmp_path)], env=ENGLISH)

        assert result.exit_code == 1
        assert "No cases found" in result.output

    def test_install_without_a_target(self) -> None:
        result = runner.invoke(app, ["install"], env=ENGLISH)

        assert result.exit_code == 1
        assert "Say which tools to install into" in result.output
        assert not HANGUL.search(result.output)

    def test_korean_locale_gives_korean_without_ddk_lang(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["status", "--repo", str(tmp_path)],
            env={"DDK_LANG": None, "LC_ALL": None, "LANG": "ko_KR.UTF-8"},
        )

        assert "조회할 case가 없습니다" in result.output

    def test_other_locale_gives_english_without_ddk_lang(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            ["status", "--repo", str(tmp_path)],
            env={"DDK_LANG": None, "LC_ALL": None, "LANG": "de_DE.UTF-8"},
        )

        assert "No cases found" in result.output


class TestDemo:
    @pytest.fixture(autouse=True)
    def _fakes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        async def run_demo(workdir: Path, **kwargs: Any) -> object:
            kwargs["on_update"]("generate", {})
            return _result(workdir)

        monkeypatch.setattr("ddk.cli.demo.real_services", lambda chromium_path: chromium_path)
        monkeypatch.setattr("ddk.cli.demo.check_prerequisites", lambda **_: [])
        monkeypatch.setattr("ddk.cli.demo.run_demo", run_demo)

    def test_the_story_is_told_in_english(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")], env=ENGLISH)

        assert result.exit_code == 0, result.output
        for expected in (
            "no API key needed",
            "Code generation",
            "First attempt: SSIM 0.89, 6.3% of the page differs strongly",
            "After 1 auto-fix attempt(s): SSIM 1.00",
            "Verdict: ready",
            "First-attempt screenshot",
            "ddk run <image>",
        ):
            assert expected in result.output
        assert not HANGUL.search(result.output)


def test_module_entry_point_runs_the_command_line() -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"), "DDK_LANG": "en"}
    done = subprocess.run(
        [sys.executable, "-m", "ddk", "version"],
        env=env,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )

    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("ddk ")

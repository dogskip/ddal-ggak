"""`ddk run` fail-fast preflight — validate before mutating the filesystem."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.cli import app

runner = CliRunner()

# Clear both API-key env vars so the no-key path is deterministic.
_NO_KEY_ENV = {"DDK_ANTHROPIC_API_KEY": "", "ANTHROPIC_API_KEY": ""}
_WITH_KEY_ENV = {
    "DDK_ANTHROPIC_API_KEY": "sk-ant-test-not-real",
    "ANTHROPIC_API_KEY": "",
    "DDK_LLM_PROVIDER": "anthropic",
}


def test_missing_api_key_fails_before_workspace_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "ref.png", "--prompt", "x"], env=_NO_KEY_ENV)
    assert result.exit_code == 3
    # Fail-fast: no workspace directory should have been created.
    assert not (tmp_path / ".ddk").exists()


def test_missing_image_fails_before_workspace_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["run", "does-not-exist.png", "--prompt", "x"], env=_WITH_KEY_ENV)
    assert result.exit_code == 3
    # The provider/key passed; the missing image must stop us before mutation.
    assert not (tmp_path / ".ddk").exists()


def test_undecodable_image_fails_before_workspace_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not an image")
    result = runner.invoke(app, ["run", str(broken), "--prompt", "x"], env=_WITH_KEY_ENV)
    assert result.exit_code == 3
    assert "이미지로 읽을 수 없는 파일" in result.output
    assert not (tmp_path / ".ddk").exists()

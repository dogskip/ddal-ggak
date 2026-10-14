"""Destructive legacy entry points cannot bypass verified application."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ddk.adapters.local_git import LocalGitAdapter
from ddk.cli import app


@pytest.mark.parametrize("option", ["--force", "--allow-blocked"])
def test_apply_rejects_unsafe_option_before_case_access(tmp_path: Path, option: str) -> None:
    result = CliRunner().invoke(app, ["apply", "--repo", str(tmp_path), option])
    assert result.exit_code != 0
    assert "내보내기" in result.output
    assert not list(tmp_path.iterdir())


async def test_git_rollback_cannot_reset_or_clean_any_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []

    async def record(_repository: Path, *args: str) -> str:
        calls.append(args)
        return "a" * 40

    adapter = LocalGitAdapter()
    monkeypatch.setattr(adapter, "_run_git", record)

    with pytest.raises(ValueError, match="rollback_disabled"):
        await adapter.rollback_to(tmp_path, "refs/ddk/fix/C-001/attempt-1", force=True)
    assert calls == []

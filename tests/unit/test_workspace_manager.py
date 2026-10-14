"""Tests for WorkspaceManager helpers used by Phase 5 CLI."""

from __future__ import annotations

from ddk.workspace.manager import WorkspaceManager


def test_latest_case_id_returns_highest_existing_case(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.init()
    manager.init_case("C-001")
    manager.init_case("C-003")
    manager.init_case("C-002")

    assert manager.latest_case_id() == "C-003"


def test_latest_case_id_returns_none_when_no_cases_exist(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.init()

    assert manager.latest_case_id() is None


def test_init_writes_self_ignoring_gitignore(tmp_path) -> None:
    WorkspaceManager(tmp_path).init()

    assert (tmp_path / ".ddk" / ".gitignore").read_text(encoding="utf-8").strip() == "*"


def test_init_keeps_a_gitignore_the_user_edited(tmp_path) -> None:
    manager = WorkspaceManager(tmp_path)
    manager.init()
    (tmp_path / ".ddk" / ".gitignore").write_text("cases/\n", encoding="utf-8")

    manager.init()

    assert (tmp_path / ".ddk" / ".gitignore").read_text(encoding="utf-8") == "cases/\n"

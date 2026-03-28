"""Integration tests for WorkspaceManager."""

from __future__ import annotations

import json
from pathlib import Path

from ddk.workspace.manager import WorkspaceManager


class TestWorkspaceManagerInit:
    def test_init_creates_ddk_directory(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        assert (tmp_path / ".ddk").is_dir()

    def test_init_creates_cases_subdirectory(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        assert (tmp_path / ".ddk" / "cases").is_dir()

    def test_init_creates_schema_version_file(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        schema_file = tmp_path / ".ddk" / "schema-version.json"
        assert schema_file.exists()
        data = json.loads(schema_file.read_text())
        assert "schema_version" in data

    def test_init_is_idempotent(self, tmp_path: Path) -> None:
        """Calling init() multiple times must not raise or corrupt state."""
        manager = WorkspaceManager(tmp_path)
        manager.init()
        manager.init()
        manager.init()
        assert (tmp_path / ".ddk" / "cases").is_dir()
        schema_file = tmp_path / ".ddk" / "schema-version.json"
        data = json.loads(schema_file.read_text())
        assert "schema_version" in data

    def test_root_property(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        assert manager.root == tmp_path / ".ddk"


class TestWorkspaceManagerCaseId:
    def test_next_case_id_first(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        assert manager.next_case_id() == "C-001"

    def test_next_case_id_increments(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        # Create two existing case dirs
        (tmp_path / ".ddk" / "cases" / "C-001").mkdir()
        (tmp_path / ".ddk" / "cases" / "C-002").mkdir()
        assert manager.next_case_id() == "C-003"

    def test_next_case_id_zero_pads(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        for i in range(1, 10):
            (tmp_path / ".ddk" / "cases" / f"C-{i:03d}").mkdir()
        assert manager.next_case_id() == "C-010"


class TestWorkspaceManagerInitCase:
    def test_init_case_creates_subdirs(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        case_path = manager.init_case("C-001")

        for sub in ("artifacts", "reports", "fix-attempts", "llm-calls", "screenshots"):
            assert (case_path / sub).is_dir(), f"Missing subdirectory: {sub}"

    def test_init_case_returns_case_path(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        result = manager.init_case("C-001")
        assert result == tmp_path / ".ddk" / "cases" / "C-001"

    def test_init_case_idempotent(self, tmp_path: Path) -> None:
        manager = WorkspaceManager(tmp_path)
        manager.init()
        manager.init_case("C-001")
        manager.init_case("C-001")  # must not raise
        assert (tmp_path / ".ddk" / "cases" / "C-001" / "artifacts").is_dir()

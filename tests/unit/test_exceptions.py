"""Tests for exceptions.py — DirtyWorkingTreeError, CostCapExceededError."""

from __future__ import annotations

from ddk.exceptions import CostCapExceededError, DirtyWorkingTreeError


class TestDirtyWorkingTreeError:
    def test_basic(self) -> None:
        err = DirtyWorkingTreeError(
            repo_path="/tmp/repo",
            modified=["file1.txt"],
            staged=["file2.txt"],
        )
        assert isinstance(err, RuntimeError)
        assert err.repo_path == "/tmp/repo"
        assert err.modified == ["file1.txt"]
        assert err.staged == ["file2.txt"]
        assert "dirty" in str(err).lower() or "/tmp/repo" in str(err)

    def test_empty_lists(self) -> None:
        err = DirtyWorkingTreeError(
            repo_path="/repo",
            modified=[],
            staged=[],
        )
        assert err.modified == []
        assert err.staged == []

    def test_is_runtime_error(self) -> None:
        err = DirtyWorkingTreeError(repo_path="/r", modified=[], staged=[])
        assert isinstance(err, RuntimeError)


class TestCostCapExceededError:
    def test_basic(self) -> None:
        err = CostCapExceededError(
            accumulated_usd=5.0,
            cap_usd=3.0,
        )
        assert isinstance(err, RuntimeError)
        assert err.accumulated_usd == 5.0
        assert err.cap_usd == 3.0
        assert "5.0" in str(err) or "cost" in str(err).lower()

    def test_is_runtime_error(self) -> None:
        err = CostCapExceededError(accumulated_usd=1.0, cap_usd=0.5)
        assert isinstance(err, RuntimeError)

    def test_exact_cap(self) -> None:
        err = CostCapExceededError(accumulated_usd=1.0, cap_usd=1.0)
        assert err.accumulated_usd == err.cap_usd

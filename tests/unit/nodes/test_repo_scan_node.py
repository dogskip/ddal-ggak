"""Tests for repo_scan_node — graph/nodes/repo_scan.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.graph.nodes.repo_scan import repo_scan_node
from ddk.models.config import DEFAULT_LIGHT_MODEL


class TestRepoScanNodeMissing:
    """Handles missing upstream state."""

    @pytest.mark.asyncio
    async def test_missing_case_input_returns_error(self) -> None:
        state: dict[str, Any] = {"case_input": None}
        result = await repo_scan_node(state)
        assert result["terminal_state"] == "manual-review-required"
        assert "case_input" in result["error_message"]


class TestRepoScanNodeSuccess:
    """Happy path delegation to RepoConventionScanner."""

    @pytest.mark.asyncio
    async def test_delegates_to_scanner(self) -> None:
        mock_case = MagicMock()
        mock_case.repo_path = "/tmp/test-repo"
        mock_profile = MagicMock()
        mock_scanner = MagicMock()
        mock_scanner.scan = AsyncMock(return_value=mock_profile)

        state: dict[str, Any] = {"case_input": mock_case}
        with patch(
            "ddk.graph.nodes.repo_scan.RepoConventionScanner",
            return_value=mock_scanner,
        ):
            result = await repo_scan_node(state)

        assert result["repo_profile"] is mock_profile
        assert result["current_node"] == "repo_scan"
        mock_scanner.scan.assert_awaited_once_with("/tmp/test-repo")

    @pytest.mark.asyncio
    async def test_uses_container_llm(self) -> None:
        mock_case = MagicMock()
        mock_case.repo_path = "/tmp/repo"
        mock_container = MagicMock()
        mock_container.llm = MagicMock()

        state: dict[str, Any] = {"case_input": mock_case}
        with patch(
            "ddk.graph.nodes.repo_scan.RepoConventionScanner",
        ) as mock_cls:
            mock_cls.return_value.scan = AsyncMock(return_value=MagicMock())
            await repo_scan_node(state, context=mock_container)

        mock_cls.assert_called_once_with(
            llm=mock_container.llm,
            model=DEFAULT_LIGHT_MODEL,
        )

    @pytest.mark.asyncio
    async def test_no_container_passes_none_llm(self) -> None:
        mock_case = MagicMock()
        mock_case.repo_path = "/tmp/repo"

        state: dict[str, Any] = {"case_input": mock_case}
        with patch(
            "ddk.graph.nodes.repo_scan.RepoConventionScanner",
        ) as mock_cls:
            mock_cls.return_value.scan = AsyncMock(return_value=MagicMock())
            await repo_scan_node(state)

        mock_cls.assert_called_once_with(
            llm=None,
            model=DEFAULT_LIGHT_MODEL,
        )

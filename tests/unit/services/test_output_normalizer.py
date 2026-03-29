"""Unit tests for OutputNormalizer service and normalize_node adapter (CODEGEN-02)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from ddk.adapters.llm.base import LLMCallConfig
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.normalization import NormalizationReport
from ddk.models.repo import RepoProfile
from ddk.services.output_normalizer import OutputNormalizer
from tests.fakes import FakeLLMAdapter

# ---------------------------------------------------------------------------
# Fake response data
# ---------------------------------------------------------------------------

_FAKE_NORM_RESPONSE = json.dumps(
    {
        "convention_fixes": [
            {
                "fix_type": "naming",
                "file_path": "src/components/my-button.tsx",
                "rule_id": "NAMING-001",
                "description": "PascalCase required",
                "before_snippet": "my-button",
                "after_snippet": "MyButton",
                "severity": "must-fix",
                "before": "my-button",
                "after": "MyButton",
            }
        ],
        "unresolved_drift": [],
        "patched_files": {},
    }
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_repo_profile() -> RepoProfile:
    return RepoProfile(framework="react")


def _make_artifacts_with_files() -> GeneratedArtifactSet:
    file = GeneratedFile(
        path="src/components/my-button.tsx",
        content="export const my-button = () => <button/>;",
        language="typescript",
        source_node_id="node-001",
        is_new=True,
    )
    return GeneratedArtifactSet(
        case_id="case-001",
        files=[file],
        file_map={file.path: file.content},
    )


def _make_empty_artifacts() -> GeneratedArtifactSet:
    return GeneratedArtifactSet(
        case_id="case-empty",
        files=[],
        file_map={},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    return FakeLLMAdapter(responses={"normalize": _FAKE_NORM_RESPONSE})


@pytest.fixture
def normalizer(fake_llm: FakeLLMAdapter) -> OutputNormalizer:
    return OutputNormalizer(llm=fake_llm)


@pytest.fixture
def artifacts_with_files() -> GeneratedArtifactSet:
    return _make_artifacts_with_files()


@pytest.fixture
def empty_artifacts() -> GeneratedArtifactSet:
    return _make_empty_artifacts()


@pytest.fixture
def repo_profile() -> RepoProfile:
    return _make_repo_profile()


# ---------------------------------------------------------------------------
# TestOutputNormalizer — 7 async tests covering OutputNormalizer.normalize()
# ---------------------------------------------------------------------------


class TestOutputNormalizer:
    async def test_normalize_returns_tuple(
        self,
        normalizer: OutputNormalizer,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """normalize() returns a 2-tuple: (NormalizationReport, GeneratedArtifactSet)."""
        result = await normalizer.normalize(artifacts_with_files, repo_profile)
        assert isinstance(result, tuple)
        assert len(result) == 2
        report, patched = result
        assert isinstance(report, NormalizationReport)
        assert isinstance(patched, GeneratedArtifactSet)

    async def test_normalize_case_id_matches(
        self,
        normalizer: OutputNormalizer,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """NormalizationReport.case_id matches artifacts.case_id."""
        report, _ = await normalizer.normalize(artifacts_with_files, repo_profile)
        assert report.case_id == artifacts_with_files.case_id

    async def test_drift_score_before_positive(
        self,
        normalizer: OutputNormalizer,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """drift_score_before > 0 when convention_fixes are present."""
        report, _ = await normalizer.normalize(artifacts_with_files, repo_profile)
        assert report.drift_score_before > 0.0

    async def test_drift_score_after_lte_before(
        self,
        normalizer: OutputNormalizer,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """drift_score_after <= drift_score_before (normalization reduces or holds drift)."""
        report, _ = await normalizer.normalize(artifacts_with_files, repo_profile)
        assert report.drift_score_after <= report.drift_score_before

    async def test_empty_artifacts_shortcircuits(
        self,
        fake_llm: FakeLLMAdapter,
        empty_artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """Empty artifacts (files=[]) returns empty NormalizationReport, 0 LLM calls."""
        normalizer = OutputNormalizer(llm=fake_llm)
        report, patched = await normalizer.normalize(empty_artifacts, repo_profile)
        assert isinstance(report, NormalizationReport)
        assert report.convention_fixes == []
        assert report.drift_score_before == 0.0
        assert report.drift_score_after == 0.0
        assert len(fake_llm.call_log) == 0  # no LLM call made
        assert patched is empty_artifacts  # same object returned

    async def test_model_is_haiku(
        self,
        fake_llm: FakeLLMAdapter,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """OutputNormalizer uses model=claude-3-haiku-20240307."""
        normalizer = OutputNormalizer(llm=fake_llm)
        await normalizer.normalize(artifacts_with_files, repo_profile)
        assert len(fake_llm.call_log) == 1
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.model == "claude-3-haiku-20240307"

    async def test_temperature_is_zero(
        self,
        fake_llm: FakeLLMAdapter,
        artifacts_with_files: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> None:
        """OutputNormalizer uses temperature=0.0 for determinism."""
        normalizer = OutputNormalizer(llm=fake_llm)
        await normalizer.normalize(artifacts_with_files, repo_profile)
        config: LLMCallConfig = fake_llm.call_log[0]["config"]
        assert config.temperature == 0.0


# ---------------------------------------------------------------------------
# TestNormalizeNode — 2 async tests for normalize_node thin adapter
# ---------------------------------------------------------------------------


class TestNormalizeNode:
    async def test_normalize_node_thin_adapter(self, fake_llm: FakeLLMAdapter) -> None:
        """normalize_node reads state, calls OutputNormalizer, writes normalization_report."""
        from ddk.graph.context import ServiceContainer
        from ddk.graph.nodes.normalize import normalize_node

        state: dict[str, Any] = {
            "generated_artifacts": _make_artifacts_with_files(),
            "repo_profile": _make_repo_profile(),
        }

        container = MagicMock(spec=ServiceContainer)
        container.llm = fake_llm

        result = await normalize_node(state, context=container)

        assert "normalization_report" in result
        assert "generated_artifacts" in result
        assert result["current_node"] == "normalize"
        assert isinstance(result["normalization_report"], NormalizationReport)
        assert isinstance(result["generated_artifacts"], GeneratedArtifactSet)

    async def test_normalize_node_guards_none_artifacts(self, fake_llm: FakeLLMAdapter) -> None:
        """normalize_node with None artifacts must enter manual-review-required."""
        from ddk.graph.context import ServiceContainer
        from ddk.graph.nodes.normalize import normalize_node

        state: dict[str, Any] = {
            "generated_artifacts": None,
            "repo_profile": _make_repo_profile(),
        }

        container = MagicMock(spec=ServiceContainer)
        container.llm = fake_llm

        result = await normalize_node(state, context=container)
        assert result.get("terminal_state") == "manual-review-required"
        assert "error_message" in result

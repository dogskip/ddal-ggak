"""TDD tests for GeneratedArtifactSet + GeneratedFile design-spec alignment (03-00)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ddk.models.generation import (
    GeneratedArtifactSet,
    GeneratedFile,
    GenerationNode,
    GenerationPlan,
)


class TestGeneratedFileDesignSpecFields:
    """GeneratedFile must have is_new and original_content fields per 12-data-models.md §4."""

    def test_is_new_default_false(self) -> None:
        gf = GeneratedFile(path="x.tsx", content="code", source_node_id="n1")
        assert gf.is_new is False

    def test_is_new_can_be_set_true(self) -> None:
        gf = GeneratedFile(path="x.tsx", content="code", source_node_id="n1", is_new=True)
        assert gf.is_new is True

    def test_original_content_default_none(self) -> None:
        gf = GeneratedFile(path="x.tsx", content="code", source_node_id="n1")
        assert gf.original_content is None

    def test_original_content_can_be_set(self) -> None:
        gf = GeneratedFile(
            path="x.tsx",
            content="new code",
            source_node_id="n1",
            original_content="old code",
        )
        assert gf.original_content == "old code"

    def test_existing_fields_still_present(self) -> None:
        gf = GeneratedFile(path="a.tsx", content="c", source_node_id="n1")
        assert gf.path == "a.tsx"
        assert gf.content == "c"
        assert gf.source_node_id == "n1"
        assert gf.language == "typescript"

    def test_roundtrip_with_new_fields(self) -> None:
        gf = GeneratedFile(
            path="x.tsx",
            content="new",
            source_node_id="n1",
            is_new=True,
            original_content="old",
        )
        data = gf.model_dump()
        restored = GeneratedFile.model_validate(data)
        assert restored == gf
        assert restored.is_new is True
        assert restored.original_content == "old"

    @pytest.mark.parametrize(
        "path",
        [
            "",
            "../escape.tsx",
            "src/../escape.tsx",
            "/tmp/escape.tsx",
            "C:\\temp\\escape.tsx",
            "\\\\server\\share\\escape.tsx",
        ],
    )
    def test_rejects_paths_outside_repository(self, path: str) -> None:
        with pytest.raises(ValidationError):
            GeneratedFile(path=path, content="code", source_node_id="n1")

    def test_rejects_windows_separators(self) -> None:
        with pytest.raises(ValidationError):
            GeneratedFile(
                path="src\\components\\Button.tsx",
                content="code",
                source_node_id="n1",
            )


class TestGenerationPlanPaths:
    def test_node_target_path_is_repository_relative(self) -> None:
        with pytest.raises(ValidationError):
            GenerationNode(id="n1", node_type="file", target_path="../../escape.ts")

    def test_plan_target_files_are_repository_relative(self) -> None:
        node = GenerationNode(id="n1", node_type="file", target_path="src/App.tsx")
        with pytest.raises(ValidationError):
            GenerationPlan(
                case_id="c",
                nodes=[node],
                target_files=["src/App.tsx", "../escape.ts"],
            )


class TestGeneratedArtifactSetDesignSpecFields:
    """GeneratedArtifactSet must have schema_version, changed_paths, trace."""

    def test_schema_version_default(self) -> None:
        art = GeneratedArtifactSet(case_id="c", files=[])
        assert art.schema_version == "1.0"

    def test_changed_paths_default_empty(self) -> None:
        art = GeneratedArtifactSet(case_id="c", files=[])
        assert art.changed_paths == []

    def test_trace_default_empty_dict(self) -> None:
        art = GeneratedArtifactSet(case_id="c", files=[])
        assert art.trace == {}

    def test_schema_version_can_be_set(self) -> None:
        art = GeneratedArtifactSet(case_id="c", files=[], schema_version="2.0")
        assert art.schema_version == "2.0"

    def test_changed_paths_can_be_set(self) -> None:
        art = GeneratedArtifactSet(case_id="c", files=[], changed_paths=["src/A.tsx", "src/B.tsx"])
        assert art.changed_paths == ["src/A.tsx", "src/B.tsx"]

    def test_trace_can_be_set(self) -> None:
        art = GeneratedArtifactSet(
            case_id="c", files=[], trace={"node_count": 3, "model": "claude"}
        )
        assert art.trace["node_count"] == 3

    def test_existing_fields_still_present(self) -> None:
        art = GeneratedArtifactSet(
            case_id="c",
            files=[],
            file_map={"a.tsx": "n1"},
            generation_trace=["step1"],
            total_tokens_used=500,
        )
        assert art.file_map == {"a.tsx": "n1"}
        assert art.generation_trace == ["step1"]
        assert art.total_tokens_used == 500

    def test_roundtrip_with_new_fields(self) -> None:
        art = GeneratedArtifactSet(
            case_id="c",
            files=[],
            schema_version="1.0",
            changed_paths=["src/X.tsx"],
            trace={"info": "test"},
        )
        data = art.model_dump()
        restored = GeneratedArtifactSet.model_validate(data)
        assert restored.schema_version == "1.0"
        assert restored.changed_paths == ["src/X.tsx"]
        assert restored.trace == {"info": "test"}

    def test_no_mutable_default_sharing(self) -> None:
        """Verify changed_paths uses default_factory (no shared mutable default)."""
        a1 = GeneratedArtifactSet(case_id="c1", files=[])
        a2 = GeneratedArtifactSet(case_id="c2", files=[])
        a1.changed_paths.append("src/A.tsx")
        assert a2.changed_paths == [], "Mutable default shared — use Field(default_factory=list)"

"""Repository boundaries reject protected inputs before any model or copy access."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ddk.adapters.llm.base import LLMResponse
from ddk.adapters.sandbox.tempdir import TempDirSandbox
from ddk.exceptions import GenerationError
from ddk.models.generation import (
    GeneratedArtifactSet,
    GeneratedFile,
    GenerationNode,
    GenerationPlan,
)
from ddk.models.intent import IntentGraph
from ddk.models.repo import RepoProfile
from ddk.models.validation import FailureRecord
from ddk.security.repo_paths import (
    UnsafeRepositoryPathError,
    normalize_repo_relative_path,
    resolve_within_repository,
)
from ddk.security.secret_paths import is_secret_path
from ddk.services.auto_fix_planner import AutoFixPlanner
from ddk.services.code_generator import CodeGenerator
from ddk.services.file_blocks import is_protected_path
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

PROTECTED_PATHS = [
    ".git/config",
    "nested/.git/HEAD",
    ".ddk/cases/private.json",
    ".ddk-home/.npm-cache/log",
    ".codex/auth.json",
    ".claude/settings.json",
    ".gemini/oauth_creds.json",
    ".config/gcloud/application_default_credentials.json",
    ".docker/config.json",
    ".env.example",
    ".envrc",
    ".envrc/hooks/private.ts",
    "credentials/private.ts",
    ".config/opencode/auth.json",
]


@pytest.mark.parametrize("path", PROTECTED_PATHS)
def test_protected_paths_share_context_and_change_policy(path: str) -> None:
    assert is_secret_path(path)
    assert is_protected_path(path)
    with pytest.raises(ValidationError):
        GeneratedFile(path=path, content="untrusted", source_node_id="n")


@pytest.mark.parametrize(
    "path", [r"src\App.tsx", " src/App.tsx", "src/App.tsx ", "src//App.tsx", "src/./App.tsx"]
)
def test_relative_path_requires_exact_posix_spelling(path: str) -> None:
    with pytest.raises(UnsafeRepositoryPathError):
        normalize_repo_relative_path(path)


def test_owned_artifact_paths_can_contain_ddk(tmp_path: Path) -> None:
    assert resolve_within_repository(tmp_path, ".ddk/cases/run.json") == (
        tmp_path / ".ddk/cases/run.json"
    )


@pytest.mark.parametrize("kind", ["hardlink", "fifo", "parent-file"])
def test_generic_boundary_rejects_unsafe_file_types(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    if kind == "hardlink":
        outside = tmp_path / "outside.ts"
        outside.write_text("private")
        os.link(outside, root / "target.ts")
        path = "target.ts"
    elif kind == "fifo":
        os.mkfifo(root / "target.ts")
        path = "target.ts"
    else:
        (root / "src").write_text("not a directory")
        path = "src/target.ts"
    with pytest.raises(UnsafeRepositoryPathError):
        resolve_within_repository(root, path)


async def _generate(answer: str, root: Path) -> GeneratedArtifactSet:
    return await CodeGenerator(FakeLLMAdapter({"generate": answer})).generate_all(
        GenerationPlan(
            case_id="c",
            nodes=[GenerationNode(id="n", node_type="file", target_path="src/App.tsx")],
            execution_order=["n"],
        ),
        RepoProfile(framework="react"),
        IntentGraph(
            id="c",
            source_image_hash="h",
            confidence=1.0,
            layout_regions=[],
            components=[],
            interactions=[],
        ),
        "modify the heading",
        repo_root=root,
    )


@pytest.mark.parametrize("kind", ["symlink", "parent-symlink", "hardlink", "dangling-symlink"])
async def test_generation_never_imports_linked_original(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.tsx"
    outside.write_text("private marker")
    if kind == "parent-symlink":
        folder = tmp_path / "outside"
        folder.mkdir()
        (folder / "App.tsx").write_text("private marker")
        (root / "src").symlink_to(folder, target_is_directory=True)
    else:
        (root / "src").mkdir()
        target = root / "src/App.tsx"
        if kind == "hardlink":
            os.link(outside, target)
        else:
            target.symlink_to(outside if kind == "symlink" else tmp_path / "missing")
    with (
        patch.object(Path, "read_text", side_effect=AssertionError("unsafe direct access")),
        pytest.raises(GenerationError, match="no usable file"),
    ):
        await _generate("=== FILE: src/App.tsx ===\nexport default 1;", root)


@pytest.mark.parametrize("content", [None, 12, {"source": "untrusted"}, ["untrusted"]])
async def test_json_generation_rejects_non_string_content(tmp_path: Path, content: object) -> None:
    answer = json.dumps({"files": [{"path": "src/App.tsx", "content": content}]})
    with pytest.raises(GenerationError, match="no usable file"):
        await _generate(answer, tmp_path)


async def test_truncated_repair_discards_complete_main_and_extras(tmp_path: Path) -> None:
    original = "export const value: number = 'wrong';\n"
    artifacts = GeneratedArtifactSet(
        case_id="c",
        files=[GeneratedFile(path="src/App.tsx", content=original, source_node_id="n")],
        file_map={"src/App.tsx": original},
    )
    failure = FailureRecord(
        id="f",
        taxonomy_id="FT-TYPE-001",
        severity="major",
        message="Type string is not assignable to number",
        file_path="src/App.tsx",
        raw_output="TS2322",
    )
    response = LLMResponse(
        content=(
            "export const value: number = 1;\n=== FILE: src/new.css ===\nbody { color: red; }\n"
        ),
        model="fake",
        truncated=True,
    )
    llm = FakeLLMAdapter()
    with patch.object(llm, "complete", return_value=response):
        attempt, updated = await AutoFixPlanner(llm, repo_root=tmp_path).plan_and_apply(
            [failure], artifacts, "c", 1
        )
    assert attempt.success is False
    assert attempt.files_patched == []
    assert "truncated" in attempt.patch_description
    assert updated == artifacts


@pytest.mark.parametrize("kind", ["internal-symlink", "hardlink", "fifo"])
async def test_copy_excludes_every_non_regular_or_linked_source(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "ok.ts").write_text("ordinary")
    target = root / "linked.ts"
    if kind == "internal-symlink":
        target.symlink_to("ok.ts")
    elif kind == "hardlink":
        outside = tmp_path / "private.ts"
        outside.write_text("private")
        os.link(outside, target)
    else:
        os.mkfifo(target)
    sandbox = TempDirSandbox()
    try:
        copied = await sandbox.create(root)
        assert (copied / "ok.ts").read_text() == "ordinary"
        assert not (copied / "linked.ts").exists()
        assert not (copied / "linked.ts").is_symlink()
    finally:
        await sandbox.cleanup()


@pytest.mark.parametrize("kind", ["hardlink", "backslash-name"])
def test_context_rejects_untrusted_source_identity(tmp_path: Path, kind: str) -> None:
    from ddk.services.context_pack_builder import ContextPackBuilder

    (tmp_path / "src").mkdir()
    marker = "PRIVATE-MARKER"
    if kind == "hardlink":
        (tmp_path / "private.txt").write_text(marker)
        os.link(tmp_path / "private.txt", tmp_path / "src/App.tsx")
    else:
        (tmp_path / r"src\App.tsx").write_text(marker)
    pack = ContextPackBuilder().build(target_files=["src/App.tsx"], repo_path=tmp_path)
    assert not any(marker in chunk.content for chunk in pack.chunks)


def test_artifact_set_rejects_colliding_paths() -> None:
    with pytest.raises(ValidationError, match="collid"):
        GeneratedArtifactSet(
            case_id="c",
            files=[
                GeneratedFile(path="src/App.tsx", content="a", source_node_id="n"),
                GeneratedFile(path="src/app.tsx", content="b", source_node_id="n"),
            ],
        )


async def test_generation_rejects_duplicate_file_blocks(tmp_path: Path) -> None:
    with pytest.raises(GenerationError, match="collid"):
        await _generate(
            "=== FILE: src/App.tsx ===\nexport default 1;\n"
            "=== FILE: src/App.tsx ===\nexport default 2;\n",
            tmp_path,
        )


async def test_repair_extras_cannot_traverse_dangling_parent_symlink(tmp_path: Path) -> None:
    (tmp_path / "linked").symlink_to(tmp_path / "outside-missing", target_is_directory=True)
    accepted = AutoFixPlanner(FakeLLMAdapter(), repo_root=tmp_path)._accept_extra(
        "linked/style.css", "body {}", {}
    )
    assert accepted is None


async def test_copy_refuses_symlink_repository_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "App.tsx").write_text("private")
    alias = tmp_path / "alias"
    alias.symlink_to(source, target_is_directory=True)
    sandbox = TempDirSandbox()
    try:
        with pytest.raises(UnsafeRepositoryPathError, match="symlink"):
            await sandbox.create(alias)
    finally:
        await sandbox.cleanup()


@pytest.mark.parametrize("second_path", ["src/new.css", "src/New.css"])
async def test_repair_rejects_colliding_extra_files(tmp_path: Path, second_path: str) -> None:
    original = "export const value: number = 'wrong';\n"
    artifacts = GeneratedArtifactSet(
        case_id="c",
        files=[GeneratedFile(path="src/App.tsx", content=original, source_node_id="n")],
    )
    failure = FailureRecord(
        id="f",
        taxonomy_id="FT-TYPE-001",
        severity="major",
        message="wrong type",
        file_path="src/App.tsx",
        raw_output="TS2322",
    )
    answer = (
        "export const value: number = 1;\n"
        "=== FILE: src/new.css ===\nbody { color: red; }\n"
        f"=== FILE: {second_path} ===\nbody {{ color: blue; }}\n"
    )
    attempt, updated = await AutoFixPlanner(
        FakeLLMAdapter({"autofix": answer}), repo_root=tmp_path
    ).plan_and_apply([failure], artifacts, "c", 1)
    assert attempt.success is False
    assert "collid" in attempt.patch_description
    assert updated == artifacts


@pytest.mark.parametrize("folder", ["node_modules", "packages/web/node_modules", ".venv"])
async def test_source_copy_skips_large_installed_dependencies(tmp_path: Path, folder: str) -> None:
    root = tmp_path / "repo"
    dependency = root / folder / "typescript/lib/typescript.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_bytes(b"d" * (2 * 1024 * 1024 + 1))
    source = root / "src/App.tsx"
    source.parent.mkdir()
    source.write_text("export default 1;\n")
    sandbox = TempDirSandbox()
    try:
        copied = await sandbox.create(root)
        assert (copied / "src/App.tsx").read_text() == "export default 1;\n"
        assert not (copied / folder).exists()
        assert dependency.stat().st_size == 2 * 1024 * 1024 + 1
    finally:
        await sandbox.cleanup()


@pytest.mark.parametrize("path", ["node_modules/react/index.js", "packages/web/node_modules/x.js"])
def test_dependencies_cannot_be_source_or_model_changes(tmp_path: Path, path: str) -> None:
    from ddk.security.repo_paths import read_source

    with (
        patch("ddk.security.file_access.read_regular") as access,
        pytest.raises(UnsafeRepositoryPathError),
    ):
        read_source(tmp_path, path)
    access.assert_not_called()
    with pytest.raises(ValidationError):
        GeneratedFile(path=path, content="untrusted", source_node_id="n")


def test_ordinary_source_still_has_two_mib_limit(tmp_path: Path) -> None:
    from ddk.security.repo_paths import read_source

    source = tmp_path / "large.ts"
    source.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="file_size_limit"):
        read_source(tmp_path, "large.ts")

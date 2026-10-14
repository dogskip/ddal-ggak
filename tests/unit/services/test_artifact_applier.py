"""ArtifactApplier copies a finished case into the repository without losing anyone's work."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.services.artifact_applier import ArtifactApplier, FileChange


def _file(
    path: str, content: str, *, original: str | None = None, is_new: bool = False
) -> GeneratedFile:
    return GeneratedFile(
        path=path,
        content=content,
        source_node_id="n1",
        is_new=is_new,
        original_content=original,
    )


def _set(*files: GeneratedFile) -> GeneratedArtifactSet:
    return GeneratedArtifactSet(case_id="C-001", files=list(files))


def _actions(changes: list[FileChange]) -> dict[str, str]:
    return {change.path: change.action for change in changes}


def test_new_file_is_created(tmp_path: Path) -> None:
    changes = ArtifactApplier().plan(_set(_file("src/Card.tsx", "x", is_new=True)), tmp_path)

    assert _actions(changes) == {"src/Card.tsx": "create"}


def test_existing_file_that_is_still_as_generated_from_is_updated(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.tsx").write_text("old\n")

    changes = ArtifactApplier().plan(
        _set(_file("src/App.tsx", "new\n", original="old\n")), tmp_path
    )

    assert _actions(changes) == {"src/App.tsx": "update"}


def test_file_already_equal_to_the_result_is_unchanged(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("same\n")

    changes = ArtifactApplier().plan(_set(_file("a.ts", "same\n", original="older\n")), tmp_path)

    assert _actions(changes) == {"a.ts": "unchanged"}


def test_file_edited_after_the_run_is_a_conflict(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("my own edit\n")

    changes = ArtifactApplier().plan(_set(_file("a.ts", "new\n", original="old\n")), tmp_path)

    assert _actions(changes) == {"a.ts": "conflict"}


def test_file_created_by_someone_else_since_the_run_is_a_conflict(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("theirs\n")

    changes = ArtifactApplier().plan(_set(_file("a.ts", "mine\n", is_new=True)), tmp_path)

    assert _actions(changes) == {"a.ts": "conflict"}


@pytest.mark.parametrize(
    "path",
    ["../outside.ts", "/etc/passwd", ".env", "config/id_rsa", "package.json", "tsconfig.json"],
)
def test_paths_that_must_never_be_written_are_rejected(tmp_path: Path, path: str) -> None:
    artifacts = GeneratedArtifactSet.model_construct(
        case_id="C-001", files=[_file("ok.ts", "x", is_new=True).model_copy(update={"path": path})]
    )

    changes = ArtifactApplier().plan(artifacts, tmp_path)

    assert _actions(changes) == {path: "rejected"}
    assert changes[0].reason


def test_symlinked_parent_directory_is_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").symlink_to(outside, target_is_directory=True)

    changes = ArtifactApplier().plan(_set(_file("src/a.ts", "x", is_new=True)), repo)

    assert _actions(changes) == {"src/a.ts": "rejected"}


def test_write_creates_directories_and_files(tmp_path: Path) -> None:
    applier = ArtifactApplier()
    changes = applier.plan(_set(_file("src/ui/Card.tsx", "card\n", is_new=True)), tmp_path)

    written = applier.write(changes, tmp_path)

    assert [c.path for c in written] == ["src/ui/Card.tsx"]
    assert (tmp_path / "src/ui/Card.tsx").read_text() == "card\n"


def test_rejected_file_blocks_the_entire_batch(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("same\n")
    applier = ArtifactApplier()
    changes = applier.plan(
        _set(_file("a.ts", "same\n", original="x"), _file("b.ts", "b", is_new=True)), tmp_path
    )
    changes.append(FileChange("../evil.ts", "rejected", "nope", reason="outside"))

    written = applier.write(changes, tmp_path)

    assert written == []
    assert not (tmp_path / "b.ts").exists()
    assert (tmp_path / "a.ts").read_text() == "same\n"
    assert not (tmp_path.parent / "evil.ts").exists()


def test_conflicts_are_not_overwritten_without_force(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("my edit\n")
    applier = ArtifactApplier()
    changes = applier.plan(_set(_file("a.ts", "new\n", original="old\n")), tmp_path)

    written = applier.write(changes, tmp_path)

    assert written == []
    assert (tmp_path / "a.ts").read_text() == "my edit\n"


def test_forced_overwrite_is_rejected_without_changing_files(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("my edit\n")
    backup = tmp_path / "backup"
    applier = ArtifactApplier()
    changes = applier.plan(_set(_file("a.ts", "new\n", original="old\n")), tmp_path)

    with pytest.raises(ValueError, match="force_disabled"):
        applier.write(changes, tmp_path, force=True, backup_dir=backup)

    assert (tmp_path / "a.ts").read_text() == "my edit\n"
    assert not backup.exists()


def test_update_also_keeps_the_replaced_version(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("old\n")
    backup = tmp_path / "backup"
    applier = ArtifactApplier()
    changes = applier.plan(_set(_file("a.ts", "new\n", original="old\n")), tmp_path)

    applier.write(changes, tmp_path, backup_dir=backup)

    assert (backup / "a.ts").read_text() == "old\n"

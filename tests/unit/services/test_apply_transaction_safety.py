"""Original changes survive failed or stale file application."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.services.artifact_applier import ArtifactApplier


def artifacts(**files: tuple[str | None, str]) -> GeneratedArtifactSet:
    return GeneratedArtifactSet(
        case_id="C-001",
        files=[
            GeneratedFile(
                path=path,
                content=after,
                original_content=before,
                is_new=before is None,
                source_node_id="n1",
            )
            for path, (before, after) in files.items()
        ],
    )


def test_deleted_original_is_conflict_not_create(tmp_path: Path) -> None:
    changes = ArtifactApplier().plan(artifacts(**{"a.ts": ("old", "new")}), tmp_path)
    assert changes[0].action == "conflict"


def test_edit_after_plan_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "a.ts"
    target.write_text("old")
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": ("old", "new")}), tmp_path)
    target.write_text("user edit")

    with pytest.raises(ValueError, match="conflict"):
        applier.write(changes, tmp_path)
    assert target.read_text() == "user edit"


def test_permission_change_after_plan_is_preserved(tmp_path: Path) -> None:
    target = tmp_path / "a.ts"
    target.write_text("old")
    target.chmod(0o640)
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": ("old", "new")}), tmp_path)
    target.chmod(0o600)

    with pytest.raises(ValueError, match="conflict"):
        applier.write(changes, tmp_path)
    assert target.read_text() == "old"
    assert target.stat().st_mode & 0o777 == 0o600


def test_create_does_not_replace_a_file_added_after_plan(tmp_path: Path) -> None:
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": (None, "new")}), tmp_path)
    (tmp_path / "a.ts").write_text("user creation")

    with pytest.raises(ValueError, match="conflict"):
        applier.write(changes, tmp_path)
    assert (tmp_path / "a.ts").read_text() == "user creation"


def test_one_conflict_prevents_all_writes(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("user edit")
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": ("old", "new"), "b.ts": (None, "new")}), tmp_path)

    assert applier.write(changes, tmp_path) == []
    assert (tmp_path / "a.ts").read_text() == "user edit"
    assert not (tmp_path / "b.ts").exists()


def test_force_never_overwrites_a_conflict(tmp_path: Path) -> None:
    (tmp_path / "a.ts").write_text("user edit")
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": ("old", "new")}), tmp_path)

    with pytest.raises(ValueError, match="force_disabled"):
        applier.write(changes, tmp_path, force=True)
    assert (tmp_path / "a.ts").read_text() == "user edit"


def test_duplicate_target_is_rejected_before_writes(tmp_path: Path) -> None:
    applier = ArtifactApplier()
    changes = applier.plan(artifacts(**{"a.ts": (None, "new")}), tmp_path)

    with pytest.raises(ValueError, match="duplicate"):
        applier.write(changes + changes, tmp_path)
    assert not (tmp_path / "a.ts").exists()


def test_second_write_failure_restores_earlier_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = tmp_path / "a.ts", tmp_path / "b.ts"
    first.write_text("old-a")
    second.write_text("old-b")
    first.chmod(0o640)
    applier = ArtifactApplier()
    changes = applier.plan(
        artifacts(**{"a.ts": ("old-a", "new-a"), "b.ts": ("old-b", "new-b")}), tmp_path
    )
    original_write = Path.write_text
    original_replace = os.replace

    def fail_write(path: Path, content: str, *args: object, **kwargs: object) -> int:
        if path == second and content == "new-b":
            raise OSError("injected second write failure")
        return original_write(path, content, *args, **kwargs)  # type: ignore[arg-type]

    def fail_replace(source: str | Path, destination: str | Path, **kwargs: object) -> None:
        directory = kwargs.get("dst_dir_fd")
        relative_target = (
            Path(destination).name == second.name
            and isinstance(directory, int)
            and os.fstat(directory).st_ino == second.parent.stat().st_ino
        )
        if Path(destination) == second or relative_target:
            raise OSError("injected second write failure")
        original_replace(source, destination, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", fail_write)
    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError, match="second write failure"):
        applier.write(changes, tmp_path, backup_dir=tmp_path / "owned-backup")
    assert first.read_text() == "old-a"
    assert second.read_text() == "old-b"
    assert first.stat().st_mode & 0o777 == 0o640

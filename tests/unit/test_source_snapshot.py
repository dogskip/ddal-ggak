"""Fixed source captures reject changes during enumeration and copying."""

from __future__ import annotations

import hashlib
import os
from unittest.mock import patch

import pytest

from ddk.models.verified_change import canonical_json
from ddk.services.source_snapshot import (
    SnapshotCancelledError,
    SnapshotChangedError,
    SnapshotError,
    capture_source,
    manifest_digest,
)


def source(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/App.tsx").write_bytes(b"approved")
    (tmp_path / "package.json").write_bytes(b"{}")
    return tmp_path


def test_manifest_has_one_fixed_utf8_representation(tmp_path):
    root = source(tmp_path)
    captured = capture_source(root)
    manifest = [
        {"path": item.path, "sha256": item.sha256, "mode": item.mode, "size_bytes": item.size_bytes}
        for item in captured.files
    ]
    assert [item["path"] for item in manifest] == ["package.json", "src/App.tsx"]
    assert captured.tree_sha256 == hashlib.sha256(canonical_json(manifest)).hexdigest()
    assert manifest_digest(reversed(captured.files)) == captured.tree_sha256
    assert captured.files[1].content == b"approved"


def test_private_files_and_dependencies_are_never_captured(tmp_path):
    root = source(tmp_path)
    for path in [
        ".env.local",
        ".git/config",
        ".ssh/id_rsa",
        "node_modules/private/data",
        ".venv/secret",
        "__pycache__/source.pyc",
    ]:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PRIVATE MUST NOT BE READ")
    result = capture_source(root)
    assert [item.path for item in result.files] == ["package.json", "src/App.tsx"]


@pytest.mark.parametrize("output", ["dist", ".next", ".turbo", "coverage"])
def test_build_outputs_are_excluded_without_excluding_nested_source_names(tmp_path, output):
    root = source(tmp_path)
    generated = root / output / "generated.js"
    generated.parent.mkdir()
    generated.write_bytes(b"generated build output")
    nested = root / "src" / output / "source.ts"
    nested.parent.mkdir()
    nested.write_bytes(b"actual source")
    result = capture_source(root)
    assert f"{output}/generated.js" not in [item.path for item in result.files]
    assert f"src/{output}/source.ts" in [item.path for item in result.files]


@pytest.mark.parametrize("change", ["edit", "add", "delete", "mode", "replace"])
def test_source_change_during_copy_is_rejected(tmp_path, change):
    root = source(tmp_path)
    import ddk.services.source_snapshot as module

    original = module.read_regular
    changed = False

    def mutate(path, max_bytes):
        nonlocal changed
        payload = original(path, max_bytes)
        if not changed:
            changed = True
            target = root / "src/App.tsx"
            if change == "edit":
                target.write_bytes(b"foreign bytes")
            elif change == "add":
                (root / "src/added.tsx").write_bytes(b"new")
            elif change == "delete":
                target.unlink()
            elif change == "mode":
                target.chmod(0o600)
            else:
                target.unlink()
                target.write_bytes(b"approved")
        return payload

    with (
        patch.object(module, "read_regular", side_effect=mutate),
        pytest.raises(SnapshotChangedError, match="snapshot_changed"),
    ):
        capture_source(root)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "fifo"])
def test_nonexclusive_regular_inputs_are_rejected(tmp_path, kind):
    root = source(tmp_path)
    if kind == "symlink":
        (root / "alias").symlink_to(root / "src/App.tsx")
    elif kind == "hardlink":
        os.link(root / "src/App.tsx", root / "alias")
    else:
        os.mkfifo(root / "pipe")
    with pytest.raises(SnapshotError):
        capture_source(root)


def test_depth_and_size_limits_fail_before_unbounded_copy(tmp_path):
    root = source(tmp_path)
    target = root / "a/b/c/value"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"12345")
    with pytest.raises(SnapshotError, match="depth"):
        capture_source(root, max_depth=2)
    with pytest.raises(SnapshotError, match="size"):
        capture_source(root, max_file_bytes=2)
    with pytest.raises(SnapshotError, match="total"):
        capture_source(root, max_total_bytes=3)
    with pytest.raises(SnapshotError, match="count"):
        capture_source(root, max_files=1)


def test_cancelled_capture_does_not_return_a_partial_snapshot(tmp_path):
    with pytest.raises(SnapshotCancelledError, match="cancelled"):
        capture_source(source(tmp_path), cancelled=lambda: True)


def test_directory_breadth_is_bounded_even_when_no_files_exist(tmp_path):
    for index in range(3):
        (tmp_path / f"empty-{index}").mkdir()
    with pytest.raises(SnapshotError, match="count"):
        capture_source(tmp_path, max_files=1)


def test_an_explicit_dependency_or_private_directory_is_not_a_source_root(tmp_path):
    root = tmp_path / "node_modules"
    root.mkdir()
    (root / "app.js").write_bytes(b"private dependency")
    with pytest.raises(SnapshotError, match="root"):
        capture_source(root)


def test_real_concurrent_parent_replacement_is_detected(tmp_path):
    import threading

    import ddk.services.source_snapshot as module

    root = source(tmp_path)
    copied = threading.Event()
    modified = threading.Event()
    original = module.read_regular
    first = True

    def edit():
        assert copied.wait(2)
        (root / "src").rename(root / "old-src")
        (root / "src").mkdir()
        (root / "src/App.tsx").write_bytes(b"foreign replacement")
        modified.set()

    def pause(path, max_bytes):
        nonlocal first
        payload = original(path, max_bytes)
        if first:
            first = False
            copied.set()
            assert modified.wait(2)
        return payload

    worker = threading.Thread(target=edit)
    worker.start()
    try:
        with (
            patch.object(module, "read_regular", side_effect=pause),
            pytest.raises(SnapshotChangedError, match="snapshot_changed"),
        ):
            capture_source(root)
    finally:
        copied.set()
        worker.join(2)
    assert not worker.is_alive()
    assert (root / "src/App.tsx").read_bytes() == b"foreign replacement"


def test_same_byte_replacement_is_rejected_even_with_reused_identity(tmp_path, monkeypatch):
    """Replacement is a concurrent edit; retained file references reveal unlinked originals."""
    import stat

    import ddk.services.source_snapshot as module

    root = tmp_path / "repo"
    root.mkdir()
    source(root)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(b"approved")
    target = root / "src/App.tsx"
    replacement.chmod(stat.S_IMODE(target.stat().st_mode))
    original = module.read_regular
    changed = False

    def coarse_identity(info):
        return (info.st_dev, 0, info.st_mode, info.st_nlink, info.st_size, 0, 0)

    def replace_after_first_read(path, max_bytes):
        nonlocal changed
        payload = original(path, max_bytes)
        if not changed:
            changed = True
            os.replace(replacement, target)
        return payload

    monkeypatch.setattr(module, "file_identity", coarse_identity)
    monkeypatch.setattr(module, "read_regular", replace_after_first_read)
    with pytest.raises(SnapshotChangedError, match="snapshot_changed"):
        capture_source(root)


@pytest.mark.parametrize("outcome", ["success", "error", "cancel"])
def test_pinned_files_are_closed_on_every_capture_exit(tmp_path, monkeypatch, outcome):
    import stat

    import ddk.services.source_snapshot as module

    original_open, original_close = os.open, os.close
    original_read = module.read_regular
    active = set()
    maximum = 0
    cancelled = False

    def tracked_open(*args, **kwargs):
        nonlocal maximum
        descriptor = original_open(*args, **kwargs)
        if stat.S_ISREG(os.fstat(descriptor).st_mode):
            active.add(descriptor)
            maximum = max(maximum, len(active))
        return descriptor

    def tracked_close(descriptor):
        active.discard(descriptor)
        return original_close(descriptor)

    def read(path, limit):
        nonlocal cancelled
        assert len(active) >= 2
        if outcome == "error":
            raise OSError("read failed")
        payload = original_read(path, limit)
        cancelled = outcome == "cancel"
        return payload

    root = source(tmp_path)
    monkeypatch.setattr(os, "open", tracked_open)
    monkeypatch.setattr(os, "close", tracked_close)
    monkeypatch.setattr(module, "read_regular", read)
    if outcome == "success":
        capture_source(root)
    else:
        expected = SnapshotCancelledError if outcome == "cancel" else SnapshotChangedError
        with pytest.raises(expected):
            capture_source(root, cancelled=lambda: cancelled)
    assert maximum >= 2
    assert active == set()

"""Check safe publication, durability failures and lock ownership."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from ddk.services.durable_files import OwnedLock, atomic_write, read_regular, sync_directory

OWNER = "00000000-0000-4000-8000-000000000002"


def test_atomic_write_preserves_exact_bytes_and_private_mode(tmp_path):
    target = tmp_path / "record.json"
    atomic_write(target, b"payload")
    assert read_regular(target, 7) == b"payload"
    assert target.stat().st_mode & 0o777 == 0o600
    assert sorted(p.name for p in tmp_path.iterdir()) == ["record.json"]


def test_exclusive_write_cannot_replace_an_existing_file(tmp_path):
    target = tmp_path / "record.json"
    atomic_write(target, b"old", exclusive=True)
    with pytest.raises(FileExistsError):
        atomic_write(target, b"new", exclusive=True)
    assert target.read_bytes() == b"old"
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize("operation", ["read", "write"])
def test_file_operations_refuse_symlink_parents_and_targets(tmp_path, operation):
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "data"
    target.write_bytes(b"old")
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    file_alias = tmp_path / "file-alias"
    file_alias.symlink_to(target)
    for path in (alias / "data", file_alias):
        with pytest.raises((OSError, ValueError)):
            read_regular(path, 100) if operation == "read" else atomic_write(path, b"new")
    assert target.read_bytes() == b"old"


def test_read_refuses_hardlinks_directories_and_oversize(tmp_path):
    target = tmp_path / "record"
    target.write_bytes(b"long")
    with pytest.raises((ValueError, OSError)):
        read_regular(target, 3)
    with pytest.raises((ValueError, OSError)):
        read_regular(tmp_path, 100)
    os.link(target, tmp_path / "alias")
    with pytest.raises((ValueError, OSError)):
        read_regular(target, 100)


def test_failed_replace_preserves_old_bytes_and_removes_temporary_file(tmp_path):
    target = tmp_path / "record"
    target.write_bytes(b"old")
    with (
        patch("ddk.services.durable_files.os.replace", side_effect=OSError("injected")),
        pytest.raises(OSError, match="injected"),
    ):
        atomic_write(target, b"new")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["record"]


def test_file_fsync_failure_does_not_publish(tmp_path):
    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=OSError("no sync")),
        pytest.raises(OSError, match="no sync"),
    ):
        atomic_write(tmp_path / "record", b"new")
    assert not list(tmp_path.iterdir())


def test_directory_sync_failure_is_reported(tmp_path):
    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=OSError("unsupported")),
        pytest.raises(OSError, match="unsupported"),
    ):
        sync_directory(tmp_path)


def test_lock_is_exclusive_and_releases_only_its_own_nonce(tmp_path):
    path = tmp_path / "apply.lock"
    first = OwnedLock(path, OWNER)
    first.acquire()
    content = json.loads(path.read_bytes())
    assert content["owner_run_id"] == OWNER
    assert content["pid"] == os.getpid()
    assert content["process_start_token"]
    with pytest.raises(FileExistsError):
        OwnedLock(path, OWNER).acquire()
    content["nonce"] = "00000000-0000-4000-8000-000000000009"
    atomic_write(path, json.dumps(content).encode())
    with pytest.raises((ValueError, OSError)):
        first.release()
    assert path.exists()


def test_corrupt_lock_is_never_stolen(tmp_path):
    path = tmp_path / "apply.lock"
    path.write_bytes(b"broken")
    with pytest.raises(FileExistsError):
        OwnedLock(path, OWNER).acquire()
    assert path.read_bytes() == b"broken"


def test_owned_context_releases_after_exception(tmp_path):
    path = tmp_path / "apply.lock"
    with pytest.raises(RuntimeError), OwnedLock(path, OWNER):
        raise RuntimeError("work failed")
    assert not path.exists()


def test_partial_write_never_replaces_the_previous_record(tmp_path):
    target = tmp_path / "record"
    target.write_bytes(b"old")
    real_fdopen = os.fdopen

    class PartialStream:
        def __init__(self, descriptor, *args, **kwargs):
            self.stream = real_fdopen(descriptor, *args, **kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, payload):
            return self.stream.write(payload[:2])

        def flush(self):
            return self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    with (
        patch("ddk.services.durable_files.os.fdopen", side_effect=PartialStream),
        pytest.raises(OSError, match="incomplete_file_write"),
    ):
        atomic_write(target, b"new content")
    assert target.read_bytes() == b"old"
    assert [p.name for p in tmp_path.iterdir()] == ["record"]


def test_file_sync_precedes_publication_and_directory_sync_follows(tmp_path):
    import stat

    events = []
    real_fsync = os.fsync
    real_replace = os.replace

    def observe_sync(descriptor):
        events.append("directory" if stat.S_ISDIR(os.fstat(descriptor).st_mode) else "file")
        return real_fsync(descriptor)

    def observe_replace(*args, **kwargs):
        events.append("publish")
        return real_replace(*args, **kwargs)

    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=observe_sync),
        patch("ddk.services.durable_files.os.replace", side_effect=observe_replace),
    ):
        atomic_write(tmp_path / "record", b"complete")
    assert events == ["file", "publish", "directory"]


def test_concurrent_exclusive_writers_have_exactly_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    target = tmp_path / "record"

    def attempt(index):
        payload = str(index).encode()
        try:
            atomic_write(target, payload, exclusive=True)
        except FileExistsError:
            return None
        return payload

    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(attempt, range(24)))
    successes = [value for value in results if value is not None]
    assert successes == [target.read_bytes()]
    assert [p.name for p in tmp_path.iterdir()] == ["record"]


def test_directory_sync_failure_removes_an_unconfirmed_exclusive_record(tmp_path):
    import stat

    real_fsync = os.fsync

    def fail_directory(descriptor):
        if stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise OSError("unconfirmed directory")
        return real_fsync(descriptor)

    target = tmp_path / "record"
    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=fail_directory),
        pytest.raises(OSError, match="unconfirmed"),
    ):
        atomic_write(target, b"complete", exclusive=True)
    assert not list(tmp_path.iterdir())


def test_failure_after_exclusive_publication_cannot_leave_an_unconfirmed_record(tmp_path):
    real_unlink = os.unlink
    failed = False

    def fail_first_temporary_unlink(name, *args, **kwargs):
        nonlocal failed
        if name.startswith(".ddk-") and not failed:
            failed = True
            raise OSError("temporary unlink failed")
        return real_unlink(name, *args, **kwargs)

    with (
        patch("ddk.services.durable_files.os.unlink", side_effect=fail_first_temporary_unlink),
        pytest.raises(OSError, match="temporary unlink failed"),
    ):
        atomic_write(tmp_path / "record", b"complete", exclusive=True)
    assert not list(tmp_path.iterdir())


def test_ensure_directory_creates_private_parents_without_changing_existing_mode(tmp_path):
    from ddk.services.durable_files import ensure_directory

    tmp_path.chmod(0o755)
    target = tmp_path / "private/nested"
    ensure_directory(target)
    assert tmp_path.stat().st_mode & 0o777 == 0o755
    assert target.stat().st_mode & 0o777 == 0o700
    assert target.parent.stat().st_mode & 0o777 == 0o700
    public = tmp_path / "source/new"
    ensure_directory(public, mode=0o755)
    assert public.stat().st_mode & 0o777 == 0o755


def test_ensure_directory_does_not_follow_aliases_or_create_after_sync_failure(tmp_path):
    from ddk.services.durable_files import ensure_directory

    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "alias").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        ensure_directory(tmp_path / "alias/foreign")
    assert not list(outside.iterdir())
    with (
        patch("ddk.services.durable_files.os.fsync", side_effect=OSError("directory sync failed")),
        pytest.raises(OSError, match="directory sync failed"),
    ):
        ensure_directory(tmp_path / "partial/uncreated")
    assert (tmp_path / "partial").is_dir()
    assert not (tmp_path / "partial/uncreated").exists()


def exited_owner_lock(path):
    import subprocess
    import sys
    from pathlib import Path

    source = Path(__file__).resolve().parents[2] / "src"
    script = (
        "import sys; from pathlib import Path; "
        "from ddk.services.durable_files import OwnedLock; "
        "lock=OwnedLock(Path(sys.argv[1]),sys.argv[2]); "
        "lock.acquire(); print(lock.nonce)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(path), OWNER],
        env={**os.environ, "PYTHONPATH": str(source)},
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    return result.stdout.strip()


def resume(path, nonce, **overrides):
    flags = {
        "local_storage_confirmed": True,
        "same_host_confirmed": True,
        "quiescence_confirmed": True,
    }
    flags.update(overrides)
    return OwnedLock.resume(path, OWNER, nonce, **flags)


def test_explicit_resume_holds_a_lease_without_rewriting_the_exited_owner_record(tmp_path):
    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    payload = path.read_bytes()
    inode = path.stat().st_ino
    recovered = resume(path, nonce)
    assert path.read_bytes() == payload
    assert path.stat().st_ino == inode
    with pytest.raises((ValueError, OSError)):
        resume(path, nonce)
    recovered.release()
    assert not path.exists()


@pytest.mark.parametrize(
    "flag", ["local_storage_confirmed", "same_host_confirmed", "quiescence_confirmed"]
)
def test_resume_requires_each_explicit_confirmation(tmp_path, flag):
    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    with pytest.raises(ValueError, match="recovery_unavailable"):
        resume(path, nonce, **{flag: False})
    assert path.exists()


def test_resume_refuses_a_live_original_owner(tmp_path):
    path = tmp_path / "apply.lock"
    original = OwnedLock(path, OWNER).acquire()
    try:
        with pytest.raises(ValueError, match="owner_active"):
            resume(path, original.nonce)
    finally:
        original.release()


@pytest.mark.parametrize("mutation", ["corrupt", "mode", "symlink", "hardlink", "token", "nonce"])
def test_resume_refuses_corrupt_replaced_or_unverifiable_records(tmp_path, mutation):
    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    if mutation == "corrupt":
        path.write_bytes(b"broken")
    elif mutation == "mode":
        path.chmod(0o644)
    elif mutation == "symlink":
        path.rename(tmp_path / "original.lock")
        path.symlink_to(tmp_path / "original.lock")
    elif mutation == "hardlink":
        os.link(path, tmp_path / "alias.lock")
    else:
        record = json.loads(path.read_bytes())
        record["process_start_token" if mutation == "token" else "nonce"] = (
            "unknown-start" if mutation == "token" else "00000000-0000-4000-8000-000000000099"
        )
        atomic_write(path, json.dumps(record).encode())
    with pytest.raises((ValueError, OSError)):
        resume(path, nonce)
    assert path.lexists() if hasattr(path, "lexists") else path.exists()


def test_resume_rejects_unknown_process_state_and_supports_confirmed_pid_reuse(tmp_path):
    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    with (
        patch("ddk.services.durable_files.os.kill", side_effect=PermissionError("unknown owner")),
        pytest.raises(ValueError, match="recovery_unavailable"),
    ):
        resume(path, nonce)
    with (
        patch("ddk.services.durable_files.os.kill", return_value=None),
        patch(
            "ddk.services.durable_files._process_start_token_for",
            return_value="ps-lstart-utc-v1:Wed Jan  1 00:00:00 2020",
        ),
    ):
        recovered = resume(path, nonce)
    assert json.loads(path.read_bytes())["nonce"] == nonce
    recovered.release()


def test_atomic_write_binds_publication_to_the_previously_observed_identity(tmp_path):
    from ddk.security.file_access import file_identity

    path = tmp_path / "source.tsx"
    path.write_bytes(b"approved before")
    planned = file_identity(path.stat())
    path.unlink()
    path.write_bytes(b"foreign source")
    with pytest.raises(ValueError, match="destination_changed"):
        atomic_write(path, b"candidate", expected_identity=planned)
    assert path.read_bytes() == b"foreign source"
    assert [item.name for item in tmp_path.iterdir()] == ["source.tsx"]
    current = file_identity(path.stat())
    atomic_write(path, b"candidate", expected_identity=current)
    assert path.read_bytes() == b"candidate"


def test_resume_refuses_replacement_while_confirming_the_old_owner(tmp_path):
    import ddk.services.durable_files as module

    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    payload = path.read_bytes()
    original = module._confirm_owner_ended

    def replace_record(record):
        original(record)
        atomic_write(path, payload)

    with (
        patch.object(module, "_confirm_owner_ended", side_effect=replace_record),
        pytest.raises(ValueError, match="lock_owner_changed"),
    ):
        resume(path, nonce)
    assert path.read_bytes() == payload
    recovered = resume(path, nonce)
    recovered.release()


def test_resume_refuses_unknown_ps_state_and_unavailable_platform(tmp_path):
    import subprocess

    path = tmp_path / "apply.lock"
    nonce = exited_owner_lock(path)
    with (
        patch("ddk.services.durable_files.os.kill", return_value=None),
        patch(
            "ddk.services.durable_files._process_start_token_for",
            side_effect=subprocess.CalledProcessError(1, ["ps"]),
        ),
        pytest.raises(ValueError, match="recovery_unavailable"),
    ):
        resume(path, nonce)
    with (
        patch("ddk.services.durable_files.sys.platform", "win32"),
        pytest.raises(ValueError, match="recovery_unavailable"),
    ):
        resume(path, nonce)
    with resume(path, nonce):
        assert path.exists()
    assert not path.exists()


@pytest.mark.parametrize("resumed", [False, True])
def test_leave_locked_preserves_the_record_and_closes_only_the_owned_lease(tmp_path, resumed):
    path = tmp_path / "apply.lock"
    if resumed:
        nonce = exited_owner_lock(path)
        lock = resume(path, nonce)
    else:
        lock = OwnedLock(path, OWNER).acquire()
    payload = path.read_bytes()
    inode = path.stat().st_ino
    descriptor = lock._lease_fd
    lock.leave_locked()
    assert path.read_bytes() == payload and path.stat().st_ino == inode
    if descriptor is not None:
        with pytest.raises(OSError):
            os.fstat(descriptor)
    with pytest.raises(ValueError, match="lock_not_owned"):
        lock.release()


def test_leaving_a_context_locked_does_not_release_the_preserved_file(tmp_path):
    path = tmp_path / "apply.lock"
    with OwnedLock(path, OWNER) as lock:
        payload = path.read_bytes()
        lock.leave_locked()
    assert path.read_bytes() == payload


def test_changed_timezone_cannot_be_mistaken_for_a_reused_pid(tmp_path, monkeypatch):
    path = tmp_path / "apply.lock"
    monkeypatch.setenv("TZ", "UTC")
    original = OwnedLock(path, OWNER).acquire()
    monkeypatch.setenv("TZ", "Asia/Seoul")
    recovered = None
    try:
        with pytest.raises(ValueError, match="owner_active"):
            recovered = resume(path, original.nonce)
    finally:
        if recovered is not None:
            recovered.leave_locked()
        original.release()

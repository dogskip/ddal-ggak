"""Durable file publication and explicit lock ownership."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys
import uuid
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from ddk.models.verified_change import canonical_json, parse_record
from ddk.security.file_access import (
    file_identity,
    parent_descriptor,
    read_regular,
    read_regular_at,
)

__all__ = ["OwnedLock", "atomic_write", "ensure_directory", "read_regular", "sync_directory"]


def ensure_directory(path: Path, mode: int = 0o700) -> None:
    if mode < 0 or mode & ~0o777:
        raise ValueError("invalid_directory_mode")
    absolute = Path(os.path.abspath(path))
    descriptor = os.open(absolute.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in absolute.parts[1:]:
            try:
                os.mkdir(part, mode=mode, dir_fd=descriptor)
            except FileExistsError:
                pass
            else:
                os.fsync(descriptor)
            following = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = following
    finally:
        os.close(descriptor)


def sync_directory(path: Path) -> None:
    """Raise when the filesystem cannot confirm directory durability."""
    with parent_descriptor(path / ".sync") as (descriptor, _):
        os.fsync(descriptor)


def _existing(parent_fd: int, name: str) -> os.stat_result | None:
    try:
        value = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise ValueError("unshared_regular_file_required")
    return value


def atomic_write(
    path: Path,
    payload: bytes,
    mode: int = 0o600,
    exclusive: bool = False,
    expected_identity: tuple[int, ...] | None = None,
) -> None:
    """Publish fully synced bytes in the destination directory."""
    if mode < 0 or mode & ~0o777:
        raise ValueError("invalid_file_mode")
    with parent_descriptor(path) as (parent_fd, name):
        if exclusive:
            try:
                os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise FileExistsError(path)
            previous = None
        else:
            previous = _existing(parent_fd, name)
        if expected_identity is not None and (
            previous is None or file_identity(previous) != expected_identity
        ):
            raise ValueError("destination_changed")
        temporary = ".ddk-" + uuid.uuid4().hex + ".tmp"
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent_fd
        )
        published = False
        new_identity: tuple[int, int] | None = None
        try:
            os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            new_stat = os.fstat(descriptor)
            new_identity = (new_stat.st_dev, new_stat.st_ino)
            if new_stat.st_size != len(payload):
                raise OSError("incomplete_file_write")
            if read_regular_at(parent_fd, temporary, len(payload)) != payload:
                raise OSError("temporary_file_mismatch")
            if exclusive:
                try:
                    os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    current = None
                else:
                    raise FileExistsError(path)
            else:
                current = _existing(parent_fd, name)
            if previous is not None and (
                current is None or file_identity(previous) != file_identity(current)
            ):
                raise ValueError("destination_changed")
            if previous is None and current is not None:
                raise FileExistsError(path)
            if exclusive:
                os.link(
                    temporary,
                    name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
                published = True
                os.unlink(temporary, dir_fd=parent_fd)
            else:
                os.replace(temporary, name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            published = True
            os.fsync(parent_fd)
            actual = read_regular_at(parent_fd, name, len(payload))
            final = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                hashlib.sha256(actual).digest() != hashlib.sha256(payload).digest()
                or stat.S_IMODE(final.st_mode) != mode
                or (final.st_dev, final.st_ino) != new_identity
            ):
                raise OSError("published_file_mismatch")
        except BaseException:
            if published and exclusive:
                with suppress(FileNotFoundError):
                    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == new_identity:
                        os.unlink(name, dir_fd=parent_fd)
            raise
        finally:
            os.close(descriptor)
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=parent_fd)


def _process_start_token_for(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "lstart="],
        capture_output=True,
        text=True,
        check=True,
        timeout=5,
        env={**os.environ, "LC_ALL": "C", "TZ": "UTC"},
    )
    token = "ps-lstart-utc-v1:" + result.stdout.strip()
    if not _valid_start_token(token):
        raise ValueError("recovery_unavailable:process_start_unknown")
    return token


def _process_start_token() -> str:
    return _process_start_token_for(os.getpid())


def _valid_start_token(token: str) -> bool:
    prefix = "ps-lstart-utc-v1:"
    if not token.startswith(prefix):
        return False
    token = token[len(prefix) :]
    match = re.fullmatch(
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r" +([0-9]{1,2}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) ([0-9]{4})",
        token,
    )
    if match is None:
        return False
    day_name, month_name, day, hour, minute, second, year = match.groups()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    try:
        value = datetime(
            int(year), months.index(month_name) + 1, int(day), int(hour), int(minute), int(second)
        )
    except ValueError:
        return False
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][value.weekday()] == day_name


def _confirm_owner_ended(record: dict[str, object]) -> None:
    pid = record["pid"]
    token = record["process_start_token"]
    if not isinstance(pid, int) or not isinstance(token, str) or not _valid_start_token(token):
        raise ValueError("recovery_unavailable:process_start_unknown")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return
    except OSError as error:
        raise ValueError("recovery_unavailable:process_state_unknown") from error
    try:
        current = _process_start_token_for(pid)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        raise ValueError("recovery_unavailable:process_state_unknown") from error
    if not _valid_start_token(current):
        raise ValueError("recovery_unavailable:process_start_unknown")
    if " ".join(current.split()) == " ".join(token.split()):
        raise ValueError("lock_owner_active")


def _lease(descriptor: int) -> None:
    if sys.platform not in {"darwin", "linux"}:
        raise ValueError("recovery_unavailable:flock_unsupported")
    try:
        import fcntl
    except ImportError as error:
        raise ValueError("recovery_unavailable:flock_unsupported") from error
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise
    except OSError as error:
        raise ValueError("recovery_unavailable:flock_unsupported") from error


class OwnedLock:
    """Never steal a lock, and release only the acquired file and nonce."""

    def __init__(self, path: Path, owner_run_id: str) -> None:
        self.path = path
        self.owner_run_id = owner_run_id
        self.nonce = str(uuid.uuid4())
        self._identity: tuple[int, int] | None = None
        self._lease_fd: int | None = None
        self._owned_payload: bytes | None = None

    def acquire(self) -> OwnedLock:
        if self._identity is not None:
            raise ValueError("lock_already_acquired")
        record = {
            "record_type": "lock",
            "schema_version": "verified-change/1",
            "owner_run_id": self.owner_run_id,
            "nonce": self.nonce,
            "pid": os.getpid(),
            "process_start_token": _process_start_token(),
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        }
        payload = canonical_json(record)
        parse_record(payload)
        atomic_write(self.path, payload, exclusive=True)
        value = self.path.lstat()
        self._identity = (value.st_dev, value.st_ino)
        self._owned_payload = payload
        return self

    @classmethod
    def resume(
        cls,
        path: Path,
        owner_run_id: str,
        expected_nonce: str,
        *,
        local_storage_confirmed: bool = False,
        same_host_confirmed: bool = False,
        quiescence_confirmed: bool = False,
    ) -> OwnedLock:
        if not (local_storage_confirmed and same_host_confirmed and quiescence_confirmed):
            raise ValueError("recovery_unavailable:explicit_confirmation_required")
        if sys.platform not in {"darwin", "linux"}:
            raise ValueError("recovery_unavailable:flock_unsupported")
        with parent_descriptor(path) as (parent_fd, name):
            previous = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            payload = read_regular_at(parent_fd, name, 4096)
            record = parse_record(payload)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if file_identity(current) != file_identity(previous):
                raise ValueError("lock_owner_changed")
            if (
                record["record_type"] != "lock"
                or record["owner_run_id"] != owner_run_id
                or record["nonce"] != expected_nonce
                or stat.S_IMODE(previous.st_mode) != 0o600
            ):
                raise ValueError("lock_owner_changed")
            descriptor = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent_fd
            )
            try:
                if file_identity(os.fstat(descriptor)) != file_identity(previous):
                    raise ValueError("lock_owner_changed")
                _lease(descriptor)
                if read_regular_at(parent_fd, name, 4096) != payload:
                    raise ValueError("lock_owner_changed")
                _confirm_owner_ended(record)
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    file_identity(current) != file_identity(previous)
                    or read_regular_at(parent_fd, name, 4096) != payload
                ):
                    raise ValueError("lock_owner_changed")
            except BaseException:
                os.close(descriptor)
                raise
        owned = cls(path, owner_run_id)
        owned.nonce = expected_nonce
        owned._identity = (previous.st_dev, previous.st_ino)
        owned._lease_fd = descriptor
        owned._owned_payload = payload
        return owned

    def release(self) -> None:
        if self._identity is None:
            raise ValueError("lock_not_owned")
        try:
            with parent_descriptor(self.path) as (parent_fd, name):
                payload = read_regular_at(parent_fd, name, 4096)
                record = parse_record(payload)
                current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    record["nonce"] != self.nonce
                    or record["owner_run_id"] != self.owner_run_id
                    or (current.st_dev, current.st_ino) != self._identity
                    or payload != self._owned_payload
                    or stat.S_IMODE(current.st_mode) != 0o600
                ):
                    raise ValueError("lock_owner_changed")
                os.unlink(name, dir_fd=parent_fd)
                os.fsync(parent_fd)
            self._identity = None
            self._owned_payload = None
        finally:
            if self._lease_fd is not None:
                os.close(self._lease_fd)
                self._lease_fd = None

    def leave_locked(self) -> None:
        if self._lease_fd is not None:
            os.close(self._lease_fd)
            self._lease_fd = None
        self._identity = None
        self._owned_payload = None

    def __enter__(self) -> OwnedLock:
        return self if self._lease_fd is not None else self.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._identity is not None:
            self.release()

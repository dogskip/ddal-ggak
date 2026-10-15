"""Receipts for actual owned temporary copies, including failed cleanup."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from uuid import uuid4

from ddk.models.verified_change import Record
from ddk.services.verified_change_engine import record_time


class WorkspaceLease:
    def __init__(
        self,
        tree_sha256: str,
        phase: str,
        round_no: int,
        observer: Callable[[Record], None] | None = None,
    ) -> None:
        self.observer = observer
        self.record: Record = {
            "lease_id": str(uuid4()),
            "round_no": round_no,
            "phase": phase,
            "isolation_kind": "snapshot_copy",
            "base_tree_sha256": tree_sha256,
            "state": "active",
            "acquired_at": record_time(),
            "released_at": None,
        }
        self._directory: tempfile.TemporaryDirectory[str] | None = None

    def _emit(self) -> None:
        if self.observer is not None:
            self.observer(dict(self.record))

    def __enter__(self) -> str:
        self._directory = tempfile.TemporaryDirectory(prefix="ddk-evaluate-")
        try:
            self._emit()
        except BaseException:
            self._directory.cleanup()
            raise
        return str(Path(self._directory.name).resolve())

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self._directory is not None
        try:
            self._directory.cleanup()
        except BaseException:
            self.record["state"] = "cleanup_failed"
            self._emit()
            raise
        self.record.update(state="released", released_at=record_time())
        self._emit()

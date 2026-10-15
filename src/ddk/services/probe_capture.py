"""Shared one-shot observation; project commands run only in an approved private copy."""

from __future__ import annotations

import shlex
import tempfile
from pathlib import Path

from ddk.adapters.verified_probe import capture_probe
from ddk.models.verified_change import Record


async def capture_preview_probe(
    target: str,
    output: Path,
    *,
    repository: Path,
    viewport: tuple[int, int] = (1280, 800),
    selector: str | None = None,
    reference: Path | None = None,
    confirm_execution: bool = False,
    frozen_time: str = "2026-01-01T00:00:00+00:00",
) -> Record:
    async def capture(url: str) -> Record:
        return await capture_probe(
            url,
            output,
            viewport=viewport,
            selector=selector,
            repository=repository,
            reference=reference,
            frozen_time=frozen_time,
        )

    if target.startswith(("http://", "https://")):
        return await capture(target)
    if not confirm_execution:
        raise ValueError("preview_execution_confirmation_required")
    from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
    from ddk.services.source_snapshot import capture_git_worktree, materialize_snapshot

    with tempfile.TemporaryDirectory(prefix="ddk-probe-") as folder:
        app_dir = Path(folder).resolve() / "app"
        materialize_snapshot(capture_git_worktree(repository), app_dir)
        session = await SubprocessPreviewLauncher().start(
            shlex.split(target), app_dir, timeout_s=15
        )
        try:
            return await capture(session.url)
        finally:
            await session.stop()

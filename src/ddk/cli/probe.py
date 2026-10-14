"""Headless one-shot browser evidence, separate from a canonical verdict."""

from __future__ import annotations

import asyncio
import shlex
import tempfile
from pathlib import Path
from uuid import uuid4

import typer

from ddk.adapters.verified_probe import capture_probe, register_reference
from ddk.models.verified_change import Record, decode_json
from ddk.security.file_access import read_regular
from ddk.services.verified_change_store import VerifiedChangeStore

from .app import app
from .verified import execute_command


@app.command("probe", help="Capture headless PNG, DOM, ARIA and browser error evidence.")
def probe(
    url: str = typer.Option(..., "--url"),
    viewport: str = typer.Option("1280x800", "--viewport"),
    selector: str | None = typer.Option(None, "--selector"),
    out: Path | None = typer.Option(None, "--out"),
    repo: Path = typer.Option(Path("."), "--repo"),
    reference: Path | None = typer.Option(None, "--reference"),
    update_reference: str | None = typer.Option(None, "--update-reference", "--update-baseline"),
    case_id: str | None = typer.Option(None, "--case"),
    check_id: str | None = typer.Option(None, "--check"),
    confirm_execution: bool = typer.Option(False, "--confirm-execution"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def execute() -> Record:
        values = viewport.lower().split("x")
        if len(values) != 2 or not all(v.isdecimal() for v in values):
            raise ValueError("invalid_viewport")
        size = (int(values[0]), int(values[1]))
        output = out or repo / ".ddk/probes" / str(uuid4())
        if update_reference is not None and case_id is None:
            raise ValueError("reference_case_required")
        frozen_time = "2026-01-01T00:00:00+00:00"
        if case_id is not None:
            store = VerifiedChangeStore(repo, create=False)
            store.case(case_id)
            plan = decode_json(
                read_regular(
                    store.path_for("case", case_id) / "inputs/criteria/execution.json", 2 * 1024**2
                )
            )
            frozen_time = plan["frozen_time"]
        if url.startswith(("http://", "https://")):
            result = await capture_probe(
                url,
                output,
                viewport=size,
                selector=selector,
                repository=repo,
                reference=reference,
                frozen_time=frozen_time,
            )
        else:
            if not confirm_execution:
                raise ValueError("preview_execution_confirmation_required")
            from ddk.adapters.subprocess_preview import SubprocessPreviewLauncher
            from ddk.services.source_snapshot import capture_git_worktree, materialize_snapshot

            with tempfile.TemporaryDirectory(prefix="ddk-probe-") as folder:
                app_dir = Path(folder).resolve() / "app"
                materialize_snapshot(capture_git_worktree(repo), app_dir)
                session = await SubprocessPreviewLauncher().start(
                    shlex.split(url), app_dir, timeout_s=15
                )
                try:
                    result = await capture_probe(
                        session.url,
                        output,
                        viewport=size,
                        selector=selector,
                        repository=repo,
                        reference=reference,
                        frozen_time=frozen_time,
                    )
                finally:
                    await session.stop()
        if update_reference is not None:
            assert case_id is not None
            result["case_id"] = register_reference(
                VerifiedChangeStore(repo),
                case_id,
                result,
                output,
                update_reference,
                check_id=check_id,
            )["case_id"]
        return result

    execute_command(as_json, lambda: asyncio.run(execute()))

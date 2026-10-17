"""Headless one-shot browser evidence, separate from a canonical verdict."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import typer

from ddk.adapters.verified_probe import register_reference
from ddk.i18n import t
from ddk.models.verified_change import Record, decode_json
from ddk.security.file_access import read_regular
from ddk.services.probe_capture import capture_preview_probe
from ddk.services.verified_change_store import VerifiedChangeStore

from .app import app
from .contract import warn_deprecated
from .verified import execute_command


@app.command("probe", help=t("헤드리스 PNG·DOM·ARIA와 브라우저 오류 증거를 수집합니다."))
def probe(
    url: str = typer.Option(..., "--url"),
    viewport: str = typer.Option("1280x800", "--viewport"),
    selector: str | None = typer.Option(None, "--selector"),
    out: Path | None = typer.Option(None, "--out"),
    repo: Path = typer.Option(Path("."), "--repo"),
    reference: Path | None = typer.Option(None, "--reference"),
    update_reference: str | None = typer.Option(None, "--update-reference", "--update-baseline"),
    case_id: str | None = typer.Option(None, "--case-id", "--case"),
    check_id: str | None = typer.Option(None, "--check"),
    confirm_execution: bool = typer.Option(False, "--confirm-execution"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    warn_deprecated("--case", "--case-id")

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
        result = await capture_preview_probe(
            url,
            output,
            viewport=size,
            selector=selector,
            repository=repo,
            reference=reference,
            frozen_time=frozen_time,
            confirm_execution=confirm_execution,
        )
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

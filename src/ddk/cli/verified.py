"""The verified-change commands share one service with the MCP entry point."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import typer

from ddk.models.verified_change import MAX_RECORD_BYTES, Record, decode_json
from ddk.security.file_access import read_regular

from .app import app

if TYPE_CHECKING:
    from ddk.services.verified_budget import ProviderResult
    from ddk.services.verified_change_service import VerifiedChangeService
    from ddk.services.verified_repair import RepairProvider, RepairRequest

change_app = typer.Typer(
    help="Verify existing changes, inspect evidence, export, apply, or recover.",
    no_args_is_help=True,
)
app.add_typer(change_app, name="change")
_INPUT_OR_EXECUTION_UNAVAILABLE = frozenset(
    {
        "isolation_unavailable",
        "environment_gap",
        "ambiguous_baseline",
        "baseline_mismatch",
        "ambiguous_change_requirements",
        "invalid_change_requirements",
    }
)


def _service(repository: Path) -> VerifiedChangeService:
    from ddk.services.verified_change_service import VerifiedChangeService  # noqa: PLC0415

    return VerifiedChangeService(repository)


def _repair_provider() -> RepairProvider:
    from ddk.adapters.llm.claude import ClaudeAdapter
    from ddk.adapters.verified_repair_provider import ClaudeRepairProvider

    from .common import get_config

    config = get_config()
    if not config.anthropic_api_key:
        raise ValueError("provider_api_key_required")

    async def provider(request: RepairRequest) -> ProviderResult:
        client = ClaudeAdapter(api_key=config.anthropic_api_key)
        try:
            return await ClaudeRepairProvider(client)(request)
        finally:
            await client.close()

    return provider


def _mapping(path: Path | None, *, arrays: bool = False) -> Record | None:
    if path is None:
        return None
    value = decode_json(read_regular(path, MAX_RECORD_BYTES))
    for item in value.values():
        if arrays:
            if not isinstance(item, list) or not all(
                isinstance(element, str) for element in cast(list[object], item)
            ):
                raise ValueError("change_requirements_string_arrays_required")
        elif not isinstance(item, str):
            raise ValueError("project_inputs_strings_required")
    return value


def _error_code(error: ValueError | OSError) -> str:
    code = str(error).partition(":")[0]
    if re.fullmatch(r"[a-z][a-z0-9_]*", code):
        return code
    return "file_unavailable" if isinstance(error, OSError) else "invalid_request"


def _emit(payload: Record, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        return
    for key in ("status", "decision", "assurance", "case_id", "run_id", "apply_id", "state"):
        if key in payload:
            typer.echo(f"{key}: {payload[key]}")
    if "error" in payload:
        typer.echo(f"error: {payload['error']['code']}", err=True)
    for action in payload.get("actions", []):
        parts = [str(action[key]) for key in ("code", "target", "message") if action.get(key)]
        typer.echo("action: " + " | ".join(parts))


def _exit_code(payload: Record) -> int:
    if payload.get("status") == "cancelled":
        return 130
    if payload.get("status") == "blocked" and payload.get("decision") == "ready":
        return 1
    if "decision" in payload:
        if payload["decision"] == "blocked" and any(
            action.get("code") in _INPUT_OR_EXECUTION_UNAVAILABLE
            for action in payload.get("actions", [])
        ):
            return 2
        return {"ready": 0, "blocked": 1, "manual-review": 1}.get(payload["decision"], 2)
    if "state" in payload:
        return {"applied": 0, "rolled_back": 0, "conflict": 1, "unknown": 1}.get(
            payload["state"], 2
        )
    if payload.get("status") == "blocked" and not payload.get("dry_run"):
        return 2
    return 0


def _execute(
    as_json: bool, operation: Callable[[], Record], *, identifiers: Record | None = None
) -> None:
    try:
        with redirect_stdout(sys.stderr):
            payload = operation()
    except (ValueError, OSError) as error:
        _emit(
            {
                "schema_version": "verified-change/1",
                **(identifiers or {}),
                "error": {"code": _error_code(error)},
            },
            as_json,
        )
        raise typer.Exit(2) from error
    except (KeyboardInterrupt, asyncio.CancelledError) as error:
        _emit(
            {
                "schema_version": "verified-change/1",
                **(identifiers or {}),
                "error": {"code": "cancelled"},
            },
            as_json,
        )
        raise typer.Exit(130) from error
    _emit(payload, as_json)
    raise typer.Exit(_exit_code(payload))


@change_app.command(help="Check a fixed case against explicit baseline and candidate directories.")
def verify(
    baseline: Path | None = typer.Option(None, "--baseline", help="Baseline source directory."),
    git_base: str | None = typer.Option(None, "--git-base", help="Immutable Git baseline ref."),
    candidate: Path | None = typer.Option(
        None, "--candidate", help="Candidate source directory; defaults to Git worktree."
    ),
    case: Path | None = typer.Option(None, "--case", help="Import this case definition file."),
    case_id: str | None = typer.Option(None, "--case-id", help="Use an already imported case ID."),
    inputs: Path | None = typer.Option(None, "--inputs", help="Input directory for --case."),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Stable request UUID; defaults to UUID v4."
    ),
    project_inputs: Path | None = typer.Option(
        None, "--project-inputs", help="JSON object mapping project paths to fixed input paths."
    ),
    change_requirements: Path | None = typer.Option(
        None, "--change-requirements", help="JSON object mapping changed paths to requirement IDs."
    ),
    trusted_local: bool = typer.Option(
        False,
        "--trusted-local",
        help="Explicitly approve project commands with host permissions and no OS isolation.",
    ),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository containing verified records."),
    as_json: bool = typer.Option(False, "--json", help="Output one JSON result to stdout."),
) -> None:
    selected_run_id = run_id or str(uuid4())
    identifiers: Record = {"run_id": selected_run_id}
    if case_id is not None:
        identifiers["case_id"] = case_id

    def execute() -> Record:
        if (case is None) == (case_id is None):
            raise ValueError("exactly_one_case_selection_required")
        if inputs is not None and case is None:
            raise ValueError("inputs_requires_case_file")
        mapped_inputs = _mapping(project_inputs)
        mapped_requirements = _mapping(change_requirements, arrays=True)
        service = _service(repo)
        selected_id = service.import_case(case, inputs)["case_id"] if case is not None else case_id
        assert selected_id is not None
        identifiers["case_id"] = selected_id
        return asyncio.run(
            service.verify(
                selected_id,
                baseline=baseline,
                candidate=candidate,
                run_id=selected_run_id,
                project_inputs=mapped_inputs,
                change_requirements=mapped_requirements,
                trusted_local_approved=trusted_local,
                **({"git_base": git_base} if git_base is not None else {}),
            )
        )

    _execute(as_json, execute, identifiers=identifiers)


@change_app.command(help="Repair an explicit saved candidate under one fixed request budget.")
def repair(
    source_run_id: str = typer.Option(..., "--source-run-id", help="Completed source run UUID."),
    baseline: Path = typer.Option(..., "--baseline", help="Unchanged approved baseline directory."),
    candidate: Path = typer.Option(
        ..., "--candidate", help="Exact source-run candidate directory."
    ),
    price: Path | None = typer.Option(None, "--price", help="Override the dated built-in price."),
    provider: str = typer.Option("anthropic", "--provider"),
    endpoint: str | None = typer.Option(None, "--endpoint"),
    input_token_limit: int = typer.Option(32000, "--input-token-limit", min=1, max=2**53 - 1),
    output_token_limit: int = typer.Option(4096, "--output-token-limit", min=1, max=128000),
    confirm_provider: bool = typer.Option(
        False,
        "--confirm-provider",
        help="Approve redacted scoped source transfer to the selected provider and any charges.",
    ),
    trusted_local: bool = typer.Option(
        False, "--trusted-local", help="Approve host execution for a trusted-local case."
    ),
    project_inputs: Path | None = typer.Option(None, "--project-inputs"),
    run_id: str | None = typer.Option(None, "--run-id", help="Stable repair request UUID."),
    repo: Path = typer.Option(Path("."), "--repo"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    selected = run_id or str(uuid4())

    def execute() -> Record:
        from ddk.adapters.verified_provider import select_price

        if not confirm_provider:
            raise ValueError("provider_confirmation_required")
        service = _service(repo)
        source = service.store.run(source_run_id)
        case = service.store.case(source["case_id"])
        pricing = select_price(
            provider,
            case["evaluator_sha256"],
            decode_json(read_regular(price, MAX_RECORD_BYTES)) if price else None,
            endpoint=endpoint,
        )

        async def lazy_provider(request: RepairRequest) -> ProviderResult:
            return await repair_provider(provider, endpoint)(request)

        return asyncio.run(
            service.repair(
                source_run_id,
                baseline=baseline,
                candidate=candidate,
                run_id=selected,
                price=pricing,
                input_limit=input_token_limit,
                output_limit=output_token_limit,
                provider=lazy_provider,
                provider_approved=True,
                trusted_local_approved=trusted_local,
                project_inputs=_mapping(project_inputs),
            )
        )

    _execute(as_json, execute, identifiers={"run_id": selected, "source_run_id": source_run_id})


@change_app.command(help="Read a saved run without restarting it.")
def status(
    run_id: str = typer.Option(..., "--run-id", help="Saved run UUID."),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository containing verified records."),
    as_json: bool = typer.Option(False, "--json", help="Output one JSON result to stdout."),
) -> None:
    _execute(as_json, lambda: _service(repo).status(run_id), identifiers={"run_id": run_id})


@change_app.command(help="Export saved evidence; sensitive artifacts require explicit selection.")
def export(
    run_id: str = typer.Option(..., "--run-id", help="Saved run UUID."),
    destination: Path = typer.Option(..., "--destination", help="New evidence archive file."),
    include_sensitive: bool = typer.Option(
        False,
        "--include-sensitive",
        help="Approve including sensitive evidence. Review before sharing.",
    ),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository containing verified records."),
    as_json: bool = typer.Option(False, "--json", help="Output one JSON result to stdout."),
) -> None:
    _execute(
        as_json,
        lambda: _service(repo).export(run_id, destination, include_sensitive=include_sensitive),
        identifiers={"run_id": run_id},
    )


@change_app.command(
    help="Apply an explicit ready run after confirming storage and editing conditions."
)
def apply(
    case_id: str = typer.Option(..., "--case-id", help="Case UUID."),
    run_id: str = typer.Option(..., "--run-id", help="Ready run UUID."),
    run_sha256: str = typer.Option(..., "--run-sha256", help="Complete run SHA256."),
    changes_sha256: str = typer.Option(..., "--changes-sha256", help="Changes SHA256."),
    apply_id: str | None = typer.Option(
        None, "--apply-id", help="Stable apply UUID; defaults to UUID v4."
    ),
    required_assurance: str = typer.Option(
        "isolated", "--required-assurance", help="Required assurance: isolated or trusted-local."
    ),
    confirm_local_storage: bool = typer.Option(
        False,
        "--confirm-local-storage",
        help="Confirm local storage supports durable file replacement.",
    ),
    confirm_quiescence: bool = typer.Option(
        False, "--confirm-quiescence", help="Confirm other writers and synchronization are stopped."
    ),
    repo: Path = typer.Option(Path("."), "--repo", help="Repository receiving the changes."),
    as_json: bool = typer.Option(False, "--json", help="Output one JSON result to stdout."),
) -> None:
    selected_apply_id = apply_id or str(uuid4())

    def execute() -> Record:
        if not (confirm_local_storage and confirm_quiescence):
            raise ValueError("application_confirmation_required")
        return _service(repo).apply(
            apply_id=selected_apply_id,
            case_id=case_id,
            run_id=run_id,
            run_sha256=run_sha256,
            changes_sha256=changes_sha256,
            quiescence_confirmed=confirm_quiescence,
            local_storage_confirmed=confirm_local_storage,
            required_assurance=required_assurance,
        )

    _execute(
        as_json,
        execute,
        identifiers={"case_id": case_id, "run_id": run_id, "apply_id": selected_apply_id},
    )


@change_app.command(help="Recover an owned interrupted application after explicit confirmations.")
def recover(
    apply_id: str = typer.Option(..., "--apply-id", help="Saved apply UUID."),
    confirm_local_storage: bool = typer.Option(
        False,
        "--confirm-local-storage",
        help="Confirm local storage supports durable file replacement.",
    ),
    confirm_same_host: bool = typer.Option(
        False,
        "--confirm-same-host",
        help="Confirm this is the host that owns the saved application.",
    ),
    confirm_quiescence: bool = typer.Option(
        False, "--confirm-quiescence", help="Confirm other writers and synchronization are stopped."
    ),
    repo: Path = typer.Option(
        Path("."), "--repo", help="Repository containing the owned application."
    ),
    as_json: bool = typer.Option(False, "--json", help="Output one JSON result to stdout."),
) -> None:
    def execute() -> Record:
        if not (confirm_local_storage and confirm_same_host and confirm_quiescence):
            raise ValueError("recovery_confirmation_required")
        return _service(repo).recover(
            apply_id,
            local_storage_confirmed=confirm_local_storage,
            same_host_confirmed=confirm_same_host,
            quiescence_confirmed=confirm_quiescence,
        )

    _execute(as_json, execute, identifiers={"apply_id": apply_id})


execute_command = _execute
emit_result = _emit


def repair_provider(kind: str = "anthropic", endpoint: str | None = None) -> RepairProvider:
    from ddk.adapters.verified_provider import provider_for

    return _repair_provider() if kind == "anthropic" else provider_for(kind, endpoint)

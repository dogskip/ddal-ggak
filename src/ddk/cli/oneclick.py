"""Compile and inspect fixed verification plans without manual digest assembly."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from ddk.models.verified_change import Record, decode_json
from ddk.security.file_access import read_regular
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.verified_budget import ProviderResult, VerifiedPrice
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_index import VerifiedIndexCatalog
from ddk.services.verified_repair import RepairProvider, RepairRequest

from .app import app
from .verified import change_app, execute_command, repair_provider


def select_provider(kind: str, endpoint: str | None = None) -> RepairProvider:
    import os

    from ddk.adapters.verified_provider import (
        ClaudeCliProvider,
        CodexCliProvider,
        OpenAICompatibleProvider,
    )

    if kind == "anthropic":
        return repair_provider()
    if kind == "claude-cli":
        return ClaudeCliProvider()
    if kind == "codex-cli":
        return CodexCliProvider()
    if kind == "openai-compatible" and endpoint:
        return OpenAICompatibleProvider(endpoint, api_key=os.environ.get("OPENAI_API_KEY"))
    raise ValueError("invalid_provider_selection")


@app.command(
    "init", help="Generate a fixed verification case from reviewed checks and observed inputs."
)
@change_app.command("init", help="Generate a verification case without manual hashes.")
def initialize(
    request: str = typer.Option("Verify current changes", "--request"),
    repo: Path = typer.Option(Path("."), "--repo"),
    git_base: str = typer.Option("HEAD", "--git-base"),
    from_design: Path | None = typer.Option(None, "--from-design"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    execute_command(
        as_json,
        lambda: asyncio.run(
            CaseBootstrapper(repo).initialize(
                request, git_base=git_base, from_design=from_design, dry_run=dry_run
            )
        ),
    )


@change_app.command("reindex", help="Rebuild the disposable catalog from validated canonical JSON.")
def reindex(
    repo: Path = typer.Option(Path("."), "--repo"), as_json: bool = typer.Option(False, "--json")
) -> None:
    execute_command(as_json, lambda: VerifiedIndexCatalog(VerifiedChangeStore(repo)).reindex_all())


@app.command("up", help="Snapshot, verify, optionally repair, then export and preview or apply.")
def one_command(
    request: str | None = typer.Argument(None),
    case_id: str | None = typer.Option(None, "--case"),
    repo: Path = typer.Option(Path("."), "--repo"),
    git_base: str = typer.Option("HEAD", "--git-base"),
    repair: bool = typer.Option(False, "--repair"),
    apply: bool = typer.Option(False, "--apply"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    trusted_local: bool = typer.Option(False, "--trusted-local"),
    confirm_provider: bool = typer.Option(False, "--confirm-provider"),
    provider: str = typer.Option("anthropic", "--provider"),
    endpoint: str | None = typer.Option(None, "--endpoint"),
    price: Path | None = typer.Option(None, "--price"),
    input_limit: int = typer.Option(32000, "--input-token-limit", min=1),
    output_limit: int = typer.Option(4096, "--output-token-limit", min=1, max=128000),
    confirm_quiescence: bool = typer.Option(False, "--confirm-quiescence"),
    confirm_local_storage: bool = typer.Option(False, "--confirm-local-storage"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    async def execute() -> Record:
        from ddk.adapters.verified_provider import default_price
        from ddk.services.verified_up import up

        selected_case = case_id
        if selected_case is None and not dry_run:
            initialized = await CaseBootstrapper(repo).initialize(
                request or "Verify current changes", git_base=git_base
            )
            if initialized.get("status") == "blocked":
                return initialized
            selected_case = initialized["case_id"]
        quote = None
        selected_provider = None
        if repair and confirm_provider and not dry_run:
            assert selected_case is not None
            case = VerifiedChangeStore(repo, create=False).case(selected_case)
            quote = (
                VerifiedPrice(**decode_json(read_regular(price, 2 * 1024**2)))
                if price
                else default_price("claude-sonnet-5-5", case["evaluator_sha256"])
            )
            if quote.provider != provider:
                raise ValueError("price_provider_mismatch")

            async def lazy_provider(request: RepairRequest) -> ProviderResult:
                return await select_provider(provider, endpoint)(request)

            selected_provider = lazy_provider
        return await up(
            repo,
            request,
            case_id=selected_case,
            git_base=git_base,
            dry_run=dry_run,
            repair=repair,
            apply=apply,
            trusted_local_approved=trusted_local,
            provider_approved=confirm_provider,
            provider=selected_provider,
            price=quote,
            input_limit=input_limit,
            output_limit=output_limit,
            quiescence_confirmed=confirm_quiescence,
            local_storage_confirmed=confirm_local_storage,
        )

    execute_command(as_json, lambda: asyncio.run(execute()))

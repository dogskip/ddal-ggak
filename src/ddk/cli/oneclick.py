"""Compile and inspect fixed verification plans without manual digest assembly."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from ddk.i18n import t
from ddk.models.verified_change import Record, decode_json
from ddk.security.file_access import read_regular
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.verified_budget import ProviderResult
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_index import VerifiedIndexCatalog
from ddk.services.verified_repair import RepairProvider, RepairRequest

from .app import app
from .contract import command_name, warn_deprecated
from .verified import change_app, execute_command, repair_provider


def select_provider(kind: str, endpoint: str | None = None) -> RepairProvider:
    return repair_provider(kind, endpoint)


@app.command("init", help=t("호환 명령. change init으로 고정 검증 기준을 생성합니다."))
@change_app.command("init", help=t("검토한 검사와 관측 자료로 고정 검증 기준을 생성합니다."))
def initialize(
    request: str = typer.Option("Verify current changes", "--request"),
    repo: Path = typer.Option(Path("."), "--repo"),
    git_base: str = typer.Option("HEAD", "--git-base"),
    from_design: Path | None = typer.Option(None, "--from-design"),
    discover: bool = typer.Option(False, "--discover"),
    approve_draft: bool = typer.Option(False, "--approve-draft"),
    preview: str | None = typer.Option(None, "--url"),
    confirm_execution: bool = typer.Option(False, "--confirm-execution"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    if command_name() == "init":
        warn_deprecated("init", "change init")

    async def execute() -> Record:
        if (discover and approve_draft) or (preview is not None and not discover):
            raise ValueError("invalid_init_selection")
        bootstrapper = CaseBootstrapper(repo)
        if discover:
            return await bootstrapper.discover(
                preview, confirm_execution=confirm_execution, dry_run=dry_run
            )
        if approve_draft:
            return bootstrapper.approve_draft(dry_run=dry_run)
        return await bootstrapper.initialize(
            request, git_base=git_base, from_design=from_design, dry_run=dry_run
        )

    execute_command(as_json, lambda: asyncio.run(execute()))


@change_app.command("reindex", help=t("검증한 정본 JSON으로 재생성 가능한 조회 목록을 구성합니다."))
def reindex(
    repo: Path = typer.Option(Path("."), "--repo"), as_json: bool = typer.Option(False, "--json")
) -> None:
    execute_command(as_json, lambda: VerifiedIndexCatalog(VerifiedChangeStore(repo)).reindex_all())


@app.command("up", help=t("변경을 보관·검사하고, 선택한 수정·내보내기·반영을 수행합니다."))
def one_command(
    request: str | None = typer.Argument(None),
    case_id: str | None = typer.Option(None, "--case-id", "--case"),
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
    warn_deprecated("--case", "--case-id")

    async def execute() -> Record:
        from ddk.adapters.verified_provider import select_price
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
            quote = select_price(
                provider,
                case["evaluator_sha256"],
                decode_json(read_regular(price, 2 * 1024**2)) if price else None,
                endpoint=endpoint,
            )

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

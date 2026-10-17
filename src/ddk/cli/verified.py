"""The verified-change commands share one service with the MCP entry point."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import typer

from ddk.i18n import t
from ddk.models.verified_change import MAX_RECORD_BYTES, Record, decode_json
from ddk.security.file_access import read_regular

from .app import app
from .contract import capture, command_name, exception_failure, operation_exit, warn_deprecated

if TYPE_CHECKING:
    from ddk.services.verified_budget import ProviderResult
    from ddk.services.verified_change_service import VerifiedChangeService
    from ddk.services.verified_repair import RepairProvider, RepairRequest

change_app = typer.Typer(
    help=t("기존 변경 검사·증거 조회·내보내기·반영·복구."),
    no_args_is_help=True,
)
app.add_typer(change_app, name="change")


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


def _emit(payload: Record, as_json: bool) -> None:
    if as_json:
        if capture(payload):
            return
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
    return operation_exit(command_name(), payload)


def _execute(
    as_json: bool, operation: Callable[[], Record], *, identifiers: Record | None = None
) -> None:
    try:
        with redirect_stdout(sys.stderr):
            payload = operation()
    except (ValueError, OSError, KeyboardInterrupt, asyncio.CancelledError) as error:
        if as_json and identifiers:
            capture(identifiers)
        elif not as_json and identifiers:
            _emit(
                {**identifiers, "error": {"code": exception_failure(command_name(), error).code}},
                False,
            )
        raise exception_failure(command_name(), error) from error
    _emit(payload, as_json)
    raise typer.Exit(_exit_code(payload))


@change_app.command(help=t("지정한 기준·변경 폴더를 고정 기준으로 검사합니다."))
def verify(
    baseline: Path | None = typer.Option(None, "--baseline", help=t("기준 소스 폴더.")),
    git_base: str | None = typer.Option(None, "--git-base", help=t("변경하지 않을 Git 기준 참조.")),
    candidate: Path | None = typer.Option(
        None, "--candidate", help=t("변경 후보 폴더. 기본값은 현재 Git 작업 폴더입니다.")
    ),
    case: Path | None = typer.Option(
        None, "--case-file", "--case", help=t("가져올 고정 기준 JSON 파일.")
    ),
    case_id: str | None = typer.Option(None, "--case-id", help=t("이미 등록한 기준 ID.")),
    inputs: Path | None = typer.Option(None, "--inputs", help=t("--case-file의 입력 자료 폴더.")),
    run_id: str | None = typer.Option(
        None, "--run-id", help=t("고정 요청 UUID. 기본값은 새 UUID v4입니다.")
    ),
    project_inputs: Path | None = typer.Option(
        None, "--project-inputs", help=t("프로젝트 경로와 고정 입력 경로를 연결한 JSON 객체.")
    ),
    change_requirements: Path | None = typer.Option(
        None, "--change-requirements", help=t("변경 경로와 요구사항 ID를 연결한 JSON 객체.")
    ),
    trusted_local: bool = typer.Option(
        False,
        "--trusted-local",
        help=t("프로젝트 명령의 사용자 권한 실행을 승인합니다. OS 격리는 제공하지 않습니다."),
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("검증 기록이 저장된 저장소.")),
    as_json: bool = typer.Option(
        False, "--json", help=t("표준 출력에 JSON 결과 하나를 출력합니다.")
    ),
) -> None:
    warn_deprecated("--case", "--case-file")
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


@change_app.command(help=t("고정 요청 예산 안에서 지정한 변경 후보를 수정합니다."))
def repair(
    source_run_id: str = typer.Option(..., "--source-run-id", help=t("완료된 원본 실행 UUID.")),
    baseline: Path = typer.Option(..., "--baseline", help=t("변경하지 않은 승인 기준 폴더.")),
    candidate: Path = typer.Option(..., "--candidate", help=t("원본 실행의 변경 후보 폴더.")),
    price: Path | None = typer.Option(
        None, "--price", help=t("날짜가 있는 기본 단가를 교체합니다.")
    ),
    provider: str = typer.Option("anthropic", "--provider"),
    endpoint: str | None = typer.Option(None, "--endpoint"),
    input_token_limit: int = typer.Option(32000, "--input-token-limit", min=1, max=2**53 - 1),
    output_token_limit: int = typer.Option(4096, "--output-token-limit", min=1, max=128000),
    confirm_provider: bool = typer.Option(
        False,
        "--confirm-provider",
        help=t("승인 범위의 가린 소스 전송과 제공자 비용을 승인합니다."),
    ),
    trusted_local: bool = typer.Option(
        False,
        "--trusted-local",
        help=t("사용자 권한으로 실행하며 OS 격리를 제공하지 않습니다. 명시적 승인이 필요합니다."),
    ),
    project_inputs: Path | None = typer.Option(None, "--project-inputs"),
    run_id: str | None = typer.Option(None, "--run-id", help=t("고정 수정 요청 UUID.")),
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


@change_app.command(help=t("재실행하지 않고 저장된 실행을 조회합니다."))
def status(
    run_id: str = typer.Option(..., "--run-id", help=t("저장된 실행 UUID.")),
    repo: Path = typer.Option(Path("."), "--repo", help=t("검증 기록이 저장된 저장소.")),
    as_json: bool = typer.Option(
        False, "--json", help=t("표준 출력에 JSON 결과 하나를 출력합니다.")
    ),
) -> None:
    _execute(as_json, lambda: _service(repo).status(run_id), identifiers={"run_id": run_id})


@change_app.command(help=t("저장한 증거를 내보냅니다. 민감한 자료는 명시적으로 선택해야 합니다."))
def export(
    run_id: str = typer.Option(..., "--run-id", help=t("저장된 실행 UUID.")),
    destination: Path = typer.Option(..., "--destination", help=t("새 증거 묶음 파일.")),
    include_sensitive: bool = typer.Option(
        False,
        "--include-sensitive",
        help=t("민감한 증거 포함을 승인합니다. 공유 전에 확인하세요."),
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("검증 기록이 저장된 저장소.")),
    as_json: bool = typer.Option(
        False, "--json", help=t("표준 출력에 JSON 결과 하나를 출력합니다.")
    ),
) -> None:
    _execute(
        as_json,
        lambda: _service(repo).export(run_id, destination, include_sensitive=include_sensitive),
        identifiers={"run_id": run_id},
    )


@change_app.command(help=t("저장·편집 조건을 확인한 뒤 ready 실행의 변경을 반영합니다."))
def apply(
    case_id: str = typer.Option(..., "--case-id", help=t("기준 UUID.")),
    run_id: str = typer.Option(..., "--run-id", help=t("ready 실행 UUID.")),
    run_sha256: str = typer.Option(..., "--run-sha256", help=t("전체 실행 기록 SHA256.")),
    changes_sha256: str = typer.Option(..., "--changes-sha256", help=t("변경 목록 SHA256.")),
    apply_id: str | None = typer.Option(
        None, "--apply-id", help=t("고정 반영 UUID. 기본값은 새 UUID v4입니다.")
    ),
    required_assurance: str = typer.Option(
        "isolated", "--required-assurance", help=t("필요한 실행 방식: isolated 또는 trusted-local.")
    ),
    confirm_local_storage: bool = typer.Option(
        False,
        "--confirm-local-storage",
        help=t("로컬 저장소가 내구성 있는 파일 교체를 지원함을 확인합니다."),
    ),
    confirm_quiescence: bool = typer.Option(
        False, "--confirm-quiescence", help=t("다른 편집과 동기화가 중지됐음을 확인합니다.")
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("변경을 반영할 저장소.")),
    as_json: bool = typer.Option(
        False, "--json", help=t("표준 출력에 JSON 결과 하나를 출력합니다.")
    ),
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


@change_app.command(help=t("명시적으로 확인한 뒤 중단된 소유 변경을 복구합니다."))
def recover(
    apply_id: str = typer.Option(..., "--apply-id", help=t("저장된 반영 UUID.")),
    confirm_local_storage: bool = typer.Option(
        False,
        "--confirm-local-storage",
        help=t("로컬 저장소가 내구성 있는 파일 교체를 지원함을 확인합니다."),
    ),
    confirm_same_host: bool = typer.Option(
        False,
        "--confirm-same-host",
        help=t("저장된 반영을 수행한 장비임을 확인합니다."),
    ),
    confirm_quiescence: bool = typer.Option(
        False, "--confirm-quiescence", help=t("다른 편집과 동기화가 중지됐음을 확인합니다.")
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("소유 변경이 저장된 저장소.")),
    as_json: bool = typer.Option(
        False, "--json", help=t("표준 출력에 JSON 결과 하나를 출력합니다.")
    ),
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


@change_app.command("evidence", help=t("증거 ID로 제한된 진단 자료를 조회합니다."))
def evidence(
    run_id: str = typer.Option(..., "--run-id"),
    artifact_id: str = typer.Option(..., "--artifact-id"),
    repo: Path = typer.Option(Path("."), "--repo"),
    offset: int = typer.Option(0, "--offset", min=0),
    limit: int = typer.Option(4096, "--limit", min=1, max=16384),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_evidence import read_evidence

    execute_command(
        as_json,
        lambda: read_evidence(
            VerifiedChangeStore(repo, create=False), run_id, artifact_id, offset=offset, limit=limit
        ),
    )


@change_app.command("gate", help=t("현재 Git 소스가 검증한 증거와 일치하는지 확인합니다."))
def gate(
    repo: Path = typer.Option(Path("."), "--repo"),
    case_id: str | None = typer.Option(None, "--case-id", "--case"),
    run_id: str | None = typer.Option(None, "--run-id"),
    pre_push: bool = typer.Option(
        False, "--pre-push", help=t("Git의 제한된 푸시 전 입력으로 커밋을 검증합니다.")
    ),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    from ddk.services.verified_gate import gate_status, pre_push_status

    warn_deprecated("--case", "--case-id")

    def inspect() -> Record:
        if pre_push:
            if case_id or run_id:
                raise ValueError("invalid_gate_selection")
            return pre_push_status(repo, sys.stdin.buffer.read(MAX_RECORD_BYTES + 1))
        return gate_status(repo, case_id=case_id, run_id=run_id)

    execute_command(as_json, inspect)


@change_app.command("replay", help=t("재실행 없이 봉인된 증거를 오프라인으로 재검사합니다."))
def replay(
    run_id: str = typer.Option(..., "--run-id"),
    repo: Path = typer.Option(Path("."), "--repo"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_replay import replay_run

    execute_command(as_json, lambda: replay_run(VerifiedChangeStore(repo, create=False), run_id))

"""ddalggak MCP 서버 — FastMCP 기반 Design Studio 엔진."""

import json
import os
import re
import sqlite3
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, cast

from anyio import AsyncFile
from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.stdio import stdio_server
from mcp.types import ContentBlock, ToolAnnotations
from mcp.types import Tool as MCPTool
from pydantic import Field

from ddk.models.verified_change import ContractError, Record, canonical_json
from ddk.security.mcp_stdio import BoundedStdin
from ddk.services.verified_repair import RepairProvider

if TYPE_CHECKING:
    from ddk.services.verified_change_service import VerifiedChangeService

_VERIFIED_TOOLS = frozenset(
    {
        "ddk_verify",
        "ddk_status",
        "ddk_doctor",
        "ddk_init",
        "ddk_repair",
        "ddk_probe",
        "ddk_apply",
        "ddk_query_ledger",
        "ddk_read_evidence",
        "ddk_gate_status",
        "ddk_replay",
    }
)
_UNAVAILABLE_CODES = frozenset({"isolation_unavailable", "environment_gap"})
type _PathValue = Annotated[
    str, Field(strict=True, min_length=1, max_length=4096, pattern=r"^[^\x00-\x1f\x7f]+$")
]
type _Identifier = Annotated[
    str,
    Field(
        strict=True,
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    ),
]
type _RequirementId = Annotated[str, Field(strict=True, min_length=1, max_length=128)]
type _ProjectInputs = Annotated[dict[_PathValue, _PathValue], Field(max_length=256)]
type _ChangeRequirements = Annotated[
    dict[_PathValue, Annotated[list[_RequirementId], Field(min_length=1, max_length=256)]],
    Field(max_length=20),
]


class _BoundedFastMCP(FastMCP):
    async def run_stdio_async(self) -> None:
        stdin = cast(AsyncFile[str], BoundedStdin(sys.stdin.buffer))
        async with stdio_server(stdin=stdin) as (read_stream, write_stream):
            await self._mcp_server.run(
                read_stream, write_stream, self._mcp_server.create_initialization_options()
            )

    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        for tool in tools:
            if tool.name in _VERIFIED_TOOLS:
                tool.inputSchema["additionalProperties"] = False
        return tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        if name in _VERIFIED_TOOLS:
            try:
                canonical_json({"name": name, "arguments": arguments})
            except ContractError as error:
                code = "request_size_limit" if str(error) == "record_size_limit" else "invalid_json"
                raise ToolError("invalid_tool_input:" + code) from None
            tool = next(tool for tool in await self.list_tools() if tool.name == name)
            validator = cast(Any, Draft202012Validator(tool.inputSchema))
            if next(validator.iter_errors(arguments), None):
                raise ToolError("invalid_tool_input:schema")
        return await super().call_tool(name, arguments)


mcp = _BoundedFastMCP("ddk")


def _verified_service(repository: str) -> "VerifiedChangeService":
    from ddk.services.verified_change_service import VerifiedChangeService  # noqa: PLC0415

    return VerifiedChangeService(Path(repository))


def _service_error(error: ValueError | OSError) -> ToolError:
    if isinstance(error, FileNotFoundError):
        code = "record_not_found"
    elif isinstance(error, PermissionError):
        code = "permission_denied"
    elif isinstance(error, OSError):
        code = "io_error"
    else:
        match = re.match(r"[a-z][a-z0-9_]{0,79}(?=[:;\s]|$)", str(error))
        code = match[0] if match else "verified_change_error"
    return ToolError(code)


def _verified_result(record: Record) -> str:
    return canonical_json(record).decode("utf-8")


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
    structured_output=False,
)
async def ddk_verify(
    case_id: _Identifier,
    baseline: _PathValue,
    candidate: _PathValue,
    run_id: _Identifier,
    repository: _PathValue = ".",
    project_inputs: _ProjectInputs | None = None,
    change_requirements: _ChangeRequirements | None = None,
) -> str:
    """Verify a frozen case without a model or host execution permission.

    Paths refer to this server's local filesystem. Use a stable run_id: the same
    request returns saved state; changed input with the same ID is a conflict.
    Execution requires isolation. Results and cancellation state remain queryable
    with ddk_status. Raw JSON frames are limited to 2 MiB of UTF-8 and depth 32.
    """
    try:
        record = await _verified_service(repository).verify(
            case_id,
            baseline=Path(baseline),
            candidate=Path(candidate),
            run_id=run_id,
            project_inputs=project_inputs,
            change_requirements=change_requirements,
            trusted_local_approved=False,
        )
    except (ValueError, OSError) as error:
        raise _service_error(error) from None
    for action in record.get("actions", []):
        if action.get("code") in _UNAVAILABLE_CODES:
            raise ToolError(f"{action['code']}:run_id={run_id}; query ddk_status")
    return _verified_result(record)


@mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
    structured_output=False,
)
def ddk_status(run_id: _Identifier, repository: _PathValue = ".") -> str:
    """Query the saved run by its exact ID without starting or resuming execution."""
    try:
        return _verified_result(_verified_service(repository).status(run_id))
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool()
async def design_new(
    idea: str,
    output_dir: str = ".",
    non_interactive: bool = True,
) -> str:
    """아이디어에서 10개 설계문서 생성.

    (SRS, PRD, Architecture, API, DB, Security, ADR, Test, Plan, AI Handoff)

    Args:
        idea: 프로젝트 아이디어 또는 설명 (자유 텍스트)
        output_dir: design-package/ 를 저장할 디렉토리 (기본값: 현재 디렉토리)
        non_interactive: True이면 인터뷰 없이 즉시 생성 (MCP 환경 기본값)

    Returns:
        생성된 문서 목록, 비용, 경로를 담은 JSON 문자열
    """
    from .adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415
    from .design import DesignGenerator, DesignInterviewer, DesignWriter  # noqa: PLC0415
    from .design.interviewer import InterviewResult  # noqa: PLC0415
    from .models.config import DdalggakConfig  # noqa: PLC0415

    cfg = DdalggakConfig()

    if not cfg.anthropic_api_key:
        return json.dumps(
            {
                "success": False,
                "error": "ANTHROPIC_API_KEY 미설정. 방법: export DDK_ANTHROPIC_API_KEY=sk-ant-...",
            }
        )

    llm = ClaudeAdapter(
        api_key=cfg.anthropic_api_key,
        default_model=cfg.llm_model,
        cost_cap_usd=cfg.cost_cap_usd,
    )
    out_path = Path(output_dir)

    # MCP 환경에서는 인터랙티브 인터뷰 불가 → non_interactive 기본값 True
    if non_interactive:
        interview_result: InterviewResult = InterviewResult(
            project_name=idea[:50],
            original_idea=idea,
        )
    else:
        interviewer = DesignInterviewer(llm=llm, model=cfg.llm_model)

        def ask_fn(question: str) -> str:  # pragma: no cover
            return input(f"\n{question}\n> ")

        interview_result = await interviewer.run(idea=idea, ask_fn=ask_fn)

    generator = DesignGenerator(llm=llm, model=cfg.llm_model, concurrency=3)
    gen_result = await generator.generate_all(interview_result)

    writer = DesignWriter(output_dir=out_path)
    pkg_dir = writer.write(gen_result, interview_result)

    return json.dumps(
        {
            "success": True,
            "project": interview_result.project_name,
            "documents_generated": len(gen_result.documents),
            "errors": len(gen_result.errors),
            "cost_usd": round(gen_result.total_cost_usd, 4),
            "output_dir": str(pkg_dir),
            "documents": [d.key for d in gen_result.documents],
        },
        ensure_ascii=False,
    )


@mcp.tool()
def preflight() -> str:
    """DDK 환경 점검 — API 키, Python 버전, 의존성 확인.

    Returns:
        각 항목 점검 결과를 담은 JSON 문자열
    """
    import sys  # noqa: PLC0415

    from .models.config import DdalggakConfig  # noqa: PLC0415

    results: list[dict[str, object]] = []

    py_ok = sys.version_info >= (3, 12)
    results.append({"check": "Python >= 3.12", "ok": py_ok, "detail": sys.version.split()[0]})

    try:
        cfg = DdalggakConfig()
    except Exception:  # noqa: BLE001
        cfg = DdalggakConfig.model_construct()
    api_ok = bool(cfg.anthropic_api_key)
    detail = "설정됨" if api_ok else "없음"
    results.append({"check": "DDK_ANTHROPIC_API_KEY", "ok": api_ok, "detail": detail})

    try:
        import anthropic as _  # noqa: F401, PLC0415

        results.append({"check": "anthropic SDK", "ok": True, "detail": "installed"})
    except ImportError:
        results.append(
            {
                "check": "anthropic SDK",
                "ok": False,
                "detail": "설치 필요: uv add anthropic",
            }
        )

    all_ok = all(bool(r["ok"]) for r in results)
    return json.dumps({"all_ok": all_ok, "checks": results}, ensure_ascii=False)


@mcp.tool()
def ddk_version() -> str:
    """현재 설치된 DDK 버전 반환.

    Returns:
        버전 문자열 (예: "0.1.0")
    """
    try:
        from importlib.metadata import version  # noqa: PLC0415

        return version("ddalggak")
    except Exception:  # noqa: BLE001
        return "0.0.0-dev"


def run_server() -> None:
    """MCP 서버 진입점 — stdio transport로 실행."""
    mcp.run()


def _owner_grant(capability: str, repository: str, approved: bool) -> None:
    granted = set(os.environ.get("DDK_MCP_CAPABILITIES", "").split(","))
    if not approved or capability not in granted:
        raise ToolError("owner_capability_required:" + capability)
    allowed = Path(os.environ.get("DDK_MCP_REPOSITORY", ".")).resolve()
    if Path(repository).resolve() != allowed:
        raise ToolError("repository_not_granted")


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
async def ddk_doctor(repository: _PathValue = ".") -> str:
    """Inspect local prerequisites without installing or starting project commands."""
    from ddk.services.verified_host import readiness

    return canonical_json(await readiness(Path(repository))).decode()


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False
    ),
)
async def ddk_init(
    request: Annotated[str, Field(strict=True, min_length=1, max_length=8192)],
    repository: _PathValue = ".",
    git_base: Annotated[str, Field(strict=True, min_length=1, max_length=128)] = "HEAD",
    approved: bool = False,
    dry_run: bool = True,
    discover: bool = False,
    approve_draft: bool = False,
    preview: Annotated[str | None, Field(strict=True, min_length=1, max_length=4096)] = None,
    confirm_execution: bool = False,
) -> str:
    """Compile reviewed checks into a fixed case; writes require an owner init grant."""
    if not dry_run:
        _owner_grant("init", repository, approved)
    from ddk.services.case_bootstrapper import CaseBootstrapper

    try:
        if (discover and approve_draft) or (preview is not None and not discover):
            raise ValueError("invalid_init_selection")
        bootstrapper = CaseBootstrapper(Path(repository))
        if discover:
            if preview is not None and not dry_run:
                _owner_grant("probe", repository, approved)
                if not preview.startswith(("http://", "https://")):
                    _owner_grant("trusted-local", repository, approved)
            return canonical_json(
                await bootstrapper.discover(
                    preview, dry_run=dry_run, confirm_execution=confirm_execution
                )
            ).decode()
        if approve_draft:
            return canonical_json(bootstrapper.approve_draft(dry_run=dry_run)).decode()
        return canonical_json(
            await bootstrapper.initialize(request, git_base=git_base, dry_run=dry_run)
        ).decode()
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


def _lazy_provider(kind: str, endpoint: str | None) -> RepairProvider:
    from ddk.adapters.verified_provider import provider_for
    from ddk.services.verified_budget import ProviderResult
    from ddk.services.verified_repair import RepairRequest

    async def call(request: RepairRequest) -> ProviderResult:
        return await provider_for(kind, endpoint)(request)

    return call


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
async def ddk_repair(
    source_run_id: _Identifier,
    baseline: _PathValue,
    candidate: _PathValue,
    run_id: _Identifier,
    repository: _PathValue = ".",
    approved: bool = False,
    trusted_local: bool = False,
    provider: Annotated[str, Field(strict=True, max_length=64)] = "anthropic",
    endpoint: _PathValue | None = None,
    price_json: Annotated[str, Field(strict=True, max_length=16384)] | None = None,
    input_limit: Annotated[int, Field(strict=True, ge=1, le=1000000)] = 32000,
    output_limit: Annotated[int, Field(strict=True, ge=1, le=128000)] = 4096,
) -> str:
    """Repair a source run only under both owner and per-request grants."""
    _owner_grant("repair", repository, approved)
    if trusted_local:
        _owner_grant("trusted-local", repository, approved)
    if provider == "openai-compatible":
        granted_endpoint = os.environ.get("DDK_MCP_PROVIDER_ENDPOINT")
        if (
            endpoint is None
            or granted_endpoint is None
            or endpoint.rstrip("/") != granted_endpoint.rstrip("/")
        ):
            raise ToolError("provider_endpoint_not_granted")
    elif endpoint is not None:
        raise ToolError("provider_endpoint_not_granted")
    from ddk.adapters.verified_provider import select_price
    from ddk.models.verified_change import decode_json

    service = _verified_service(repository)
    try:
        source = service.store.run(source_run_id)
        case = service.store.case(source["case_id"])
        price = select_price(
            provider,
            case["evaluator_sha256"],
            decode_json(price_json.encode()) if price_json else None,
            endpoint=endpoint,
        )
        result = await service.repair(
            source_run_id,
            baseline=Path(baseline),
            candidate=Path(candidate),
            run_id=run_id,
            price=price,
            input_limit=input_limit,
            output_limit=output_limit,
            provider=_lazy_provider(provider, endpoint),
            provider_approved=True,
            trusted_local_approved=trusted_local,
        )
        return _verified_result(result)
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True
    ),
)
async def ddk_probe(
    url: _PathValue,
    repository: _PathValue = ".",
    approved: bool = False,
    width: Annotated[int, Field(strict=True, ge=1, le=16384)] = 1280,
    height: Annotated[int, Field(strict=True, ge=1, le=16384)] = 800,
    selector: _PathValue | None = None,
) -> str:
    """Capture private browser evidence; never change criteria or apply source."""
    _owner_grant("probe", repository, approved)
    from uuid import uuid4

    from ddk.adapters.verified_probe import capture_probe

    try:
        return canonical_json(
            await capture_probe(
                url,
                Path(repository) / ".ddk/probes" / str(uuid4()),
                viewport=(width, height),
                selector=selector,
                repository=Path(repository),
            )
        ).decode()
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False
    ),
)
def ddk_apply(
    run_id: _Identifier,
    repository: _PathValue = ".",
    approved: bool = False,
    quiescence_confirmed: bool = False,
    local_storage_confirmed: bool = False,
    trusted_local: bool = False,
    apply_id: _Identifier | None = None,
    target_run_id: _Identifier | None = None,
) -> str:
    """Apply a ready record with owner permission and the existing storage confirmations."""
    _owner_grant("apply", repository, approved)
    if trusted_local:
        _owner_grant("trusted-local", repository, approved)
    from uuid import uuid4

    from ddk.models.verified_change import record_digest

    service = _verified_service(repository)
    try:
        run = service.store.run(run_id)
        return _verified_result(
            service.apply(
                apply_id=apply_id or str(uuid4()),
                case_id=run["case_id"],
                run_id=run_id,
                run_sha256=record_digest(run),
                changes_sha256=record_digest(run["changes"]),
                quiescence_confirmed=quiescence_confirmed,
                local_storage_confirmed=local_storage_confirmed,
                required_assurance="trusted-local" if trusted_local else "isolated",
                target_run_id=target_run_id,
            )
        )
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def ddk_query_ledger(
    table: Annotated[str, Field(strict=True, min_length=1, max_length=64)],
    repository: _PathValue = ".",
    limit: Annotated[int, Field(strict=True, ge=1, le=1000)] = 100,
) -> str:
    """Read a bounded catalog projection; raw requests, source and logs are excluded."""
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_index import VerifiedIndexCatalog

    try:
        safe = {
            "case_id",
            "run_id",
            "transaction_id",
            "requirement_id",
            "check_id",
            "lesson_id",
            "artifact_id",
            "call_id",
            "round_no",
            "phase",
            "status",
            "verdict",
            "state",
            "operation",
            "kind",
            "reason_code",
            "record_sha256",
            "started_at",
            "finished_at",
            "actual_cost_microusd",
            "reserved_cost_microusd",
            "total_cost_microusd",
            "size_bytes",
            "assurance_level",
            "plane",
            "bound_tree_sha256",
            "evaluator_sha256",
            "case_sha256",
            "selection_status",
            "source_artifact_id",
            "compacted_artifact_id",
            "compressor_kind",
            "raw_bytes",
            "compacted_bytes",
            "stall_category",
            "streak_count",
            "action_taken",
            "resolved_in_round",
            "resolved_patch_sha256",
            "cache_read_tokens",
            "cache_write_tokens",
            "cache_prefix_sha256",
            "lease_id",
            "isolation_kind",
            "acquired_at",
            "released_at",
        }
        rows = VerifiedIndexCatalog(VerifiedChangeStore(Path(repository), create=False)).query(
            table, limit=limit, columns=safe
        )
        return canonical_json(
            {
                "table": table,
                "derived": True,
                "rows": rows,
            }
        ).decode()
    except sqlite3.Error:
        raise _service_error(ValueError("catalog_reindex_required")) from None
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def ddk_read_evidence(
    run_id: _Identifier,
    artifact_id: Annotated[str, Field(strict=True, min_length=1, max_length=128)],
    repository: _PathValue = ".",
    offset: Annotated[int, Field(strict=True, ge=0, le=9007199254740991)] = 0,
    limit: Annotated[int, Field(strict=True, ge=1, le=16384)] = 4096,
    approved: bool = False,
) -> str:
    """Retrieve private diagnostics after the owner's repair capability approval."""
    _owner_grant("repair", repository, approved)
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_evidence import read_evidence

    try:
        return canonical_json(
            read_evidence(
                VerifiedChangeStore(Path(repository), create=False),
                run_id,
                artifact_id,
                offset=offset,
                limit=limit,
            )
        ).decode()
    except (ValueError, OSError) as error:
        raise _service_error(error) from None


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def ddk_gate_status(
    repository: _PathValue = ".",
    case_id: _Identifier | None = None,
    run_id: _Identifier | None = None,
) -> str:
    """Recheck canonical evidence and current Git source without project execution."""
    from ddk.services.verified_gate import gate_status

    return canonical_json(gate_status(Path(repository), case_id=case_id, run_id=run_id)).decode()


@mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    ),
)
def ddk_replay(run_id: _Identifier, repository: _PathValue = ".") -> str:
    """Validate existing evidence offline and return only verdict metadata."""
    from ddk.services.verified_change_store import VerifiedChangeStore
    from ddk.services.verified_replay import replay_run

    return canonical_json(
        replay_run(VerifiedChangeStore(Path(repository), create=False), run_id)
    ).decode()

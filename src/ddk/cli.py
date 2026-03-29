"""ddalggak CLI — ddk 커맨드 진입점."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from .adapters.filesystem import FilesystemAdapter
from .adapters.local_git import LocalGitAdapter
from .adapters.null_playwright import NullPlaywrightAdapter
from .adapters.sandbox.tempdir import TempDirSandbox
from .adapters.screenshot_diff_local import LocalScreenshotDiffAdapter
from .adapters.subprocess_build_runner import SubprocessBuildRunner
from .models.config import DdalggakConfig
from .models.input import CaseInput
from .services.case_artifact_store import CaseArtifactStore
from .services.pipeline_runner import PipelineRunner, RuntimeServices
from .workspace.manager import WorkspaceManager

logger = logging.getLogger(__name__)

app = typer.Typer(
    name="ddk",
    help="ddalggak — AI-powered design & development assistant",
    add_completion=False,
    rich_markup_mode="rich",
)
design_app = typer.Typer(help="Design Studio commands")
app.add_typer(design_app, name="design")

console = Console()
err_console = Console(stderr=True, style="red")


# ---------------------------------------------------------------------------
# Global options (shared state via Context)
# ---------------------------------------------------------------------------


class _State:
    config: DdalggakConfig | None = None
    dry_run: bool = False
    output_dir: Path = Path(".")


_state = _State()


@app.callback()
def main(
    ctx: typer.Context,
    case_dir: str = typer.Option("", envvar="DDK_CASE_DIR", help="Override case directory"),
    log_level: str = typer.Option("INFO", envvar="DDK_LOG_LEVEL", help="Log level"),
    dry_run: bool = typer.Option(  # noqa: B008
        False, "--dry-run", help="Show what would happen without doing it"
    ),
    output: Path = typer.Option(Path("."), "-o", "--output", help="Output directory"),  # noqa: B008
) -> None:
    """ddalggak — 아이디어를 설계문서와 코드로 변환하는 AI 어시스턴트."""
    _state.dry_run = dry_run
    _state.output_dir = output
    try:
        _state.config = DdalggakConfig()
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to load config from environment — falling back to defaults",
            exc_info=True,
        )
        _state.config = DdalggakConfig.model_construct()


# ---------------------------------------------------------------------------
# ddk --version
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Print the installed ddalggak version."""
    try:
        from importlib.metadata import version as pkg_version  # noqa: PLC0415

        ver = pkg_version("ddalggak")
    except Exception:  # noqa: BLE001
        ver = "0.0.0-dev"
    console.print(f"ddk {ver}")


# ---------------------------------------------------------------------------
# ddk preflight
# ---------------------------------------------------------------------------


@app.command()
def preflight() -> None:
    """환경 점검 — API 키, Python 버전, 의존성 확인."""
    cfg = _state.config or DdalggakConfig()
    checks: list[tuple[str, bool, str]] = []

    import sys as _sys  # noqa: PLC0415

    py_ok = _sys.version_info >= (3, 12)
    checks.append(("Python >= 3.12", py_ok, f"Python {_sys.version.split()[0]}"))

    api_ok = bool(cfg.anthropic_api_key or cfg.openai_api_key)
    checks.append(("LLM API key", api_ok, "set" if api_ok else "missing"))

    try:
        import anthropic as _  # noqa: F401, PLC0415

        checks.append(("anthropic SDK", True, "installed"))
    except ImportError:
        checks.append(("anthropic SDK", False, "not installed — run: uv add anthropic"))

    for label, ok, detail in checks:
        icon = "✅" if ok else "❌"
        console.print(f"  {icon} {label}: {detail}")

    all_ok = all(ok for _, ok, _ in checks)
    if not all_ok:
        raise typer.Exit(1)
    console.print("\n[green]All checks passed.[/green]")


# ---------------------------------------------------------------------------
# ddk design new <IDEA>
# ---------------------------------------------------------------------------


@design_app.command("new")
def design_new(
    idea: str = typer.Argument(..., help="프로젝트 아이디어 (자유 텍스트)"),
    non_interactive: bool = typer.Option(  # noqa: B008
        False, "--non-interactive", "-y", help="인터뷰 없이 바로 생성"
    ),
    output: Path = typer.Option(Path("."), "-o", "--output", help="출력 디렉토리"),  # noqa: B008
) -> None:
    """아이디어 → 인터뷰 → 10개 설계 문서 자동 생성.

    예시:
        ddk design new "쇼핑몰 만들고 싶어"
        ddk design new "AI 기반 코드 리뷰 도구" -y
    """
    cfg = _state.config or DdalggakConfig()
    out_dir = output if output != Path(".") else _state.output_dir

    _require_api_key(cfg)

    asyncio.run(_run_design_new(idea, cfg, out_dir, non_interactive))


async def _run_design_new(
    idea: str,
    cfg: DdalggakConfig,
    out_dir: Path,
    non_interactive: bool,
) -> None:
    from .adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415
    from .design import DesignGenerator, DesignInterviewer, DesignWriter  # noqa: PLC0415

    llm = ClaudeAdapter(
        api_key=cfg.anthropic_api_key,
        default_model=cfg.llm_model,
        cost_cap_usd=cfg.cost_cap_usd,
    )

    console.print(
        Panel(f"[bold cyan]Design Studio[/bold cyan]\n[white]{idea}[/white]", expand=False)
    )

    # Phase 1: Interview
    interview_result = None
    if non_interactive:
        from .design.interviewer import InterviewResult  # noqa: PLC0415

        interview_result = InterviewResult(
            project_name=idea[:50],
            original_idea=idea,
        )
    else:
        console.print("\n[bold]Step 1/2:[/bold] 요구사항 인터뷰\n")
        interviewer = DesignInterviewer(llm=llm, model=cfg.llm_model)

        def ask_fn(question: str) -> str:
            return Prompt.ask(f"\n[cyan]{question}[/cyan]")

        interview_result = await interviewer.run(idea=idea, ask_fn=ask_fn)
        console.print(
            f"\n[green]인터뷰 완료[/green] — {len(interview_result.turns)}개 질문, "
            f"{len(interview_result.extracted_requirements)}개 요구사항 도출\n"
        )

    # Phase 2: Generate 10 documents
    console.print("[bold]Step 2/2:[/bold] 설계 문서 생성 (10개)\n")

    from .design.templates import TEMPLATES  # noqa: PLC0415

    generator = DesignGenerator(llm=llm, model=cfg.llm_model, concurrency=3)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating...", total=len(TEMPLATES))

        def on_progress(key: str, current: int, total: int) -> None:
            progress.update(task, advance=1, description=f"Generating {key}...")

        gen_result = await generator.generate_all(interview_result, on_progress=on_progress)

    # Phase 3: Write to disk
    writer = DesignWriter(output_dir=out_dir)
    pkg_dir = writer.write(gen_result, interview_result)

    # Summary
    doc_count = len(gen_result.documents)
    err_count = len(gen_result.errors)
    cost = gen_result.total_cost_usd

    console.print("\n[bold green]✅ 완료![/bold green]")
    warn = f" ⚠️ {err_count}개 실패" if err_count else ""
    console.print(f"   문서: {doc_count}개 생성{warn}")
    console.print(f"   비용: ${cost:.4f} USD")
    console.print(f"   위치: [cyan]{pkg_dir}[/cyan]")

    if err_count:
        console.print(f"\n[yellow]실패한 문서:[/yellow] {', '.join(gen_result.errors.keys())}")
        console.print("  자세한 내용: design-package/ERRORS.md")


def _require_api_key(cfg: DdalggakConfig) -> None:
    if not cfg.anthropic_api_key:
        err_console.print("❌ ANTHROPIC API 키가 없습니다.")
        err_console.print("   설정 방법: export DDK_ANTHROPIC_API_KEY=sk-ant-...")
        err_console.print("            또는 export ANTHROPIC_API_KEY=sk-ant-...")
        err_console.print("   또는 .env 파일에 DDK_ANTHROPIC_API_KEY=... 추가")
        raise typer.Exit(1)


def _build_runtime_services(cfg: DdalggakConfig) -> RuntimeServices:
    """Build concrete runtime services for graph execution."""
    if cfg.llm_provider != "anthropic":
        err_console.print(f"❌ 아직 지원하지 않는 LLM provider: {cfg.llm_provider}")
        raise typer.Exit(1)

    _require_api_key(cfg)

    from .adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415

    return RuntimeServices(
        llm=ClaudeAdapter(
            api_key=cfg.anthropic_api_key,
            default_model=cfg.llm_model,
            cost_cap_usd=cfg.cost_cap_usd,
        ),
        filesystem=FilesystemAdapter(),
        git=LocalGitAdapter(),
        sandbox=TempDirSandbox(),
        build_runner=SubprocessBuildRunner(),
        browser=NullPlaywrightAdapter(),
        screenshot_diff=LocalScreenshotDiffAdapter(),
    )


def _resolve_case_path(repo: Path, case_id: str | None) -> Path:
    """Resolve a case directory, defaulting to the latest case when omitted."""
    manager = WorkspaceManager(repo.resolve())
    resolved_case_id = case_id or manager.latest_case_id()
    if resolved_case_id is None:
        err_console.print("❌ 조회할 case가 없습니다. 먼저 `ddk run`을 실행하세요.")
        raise typer.Exit(1)
    case_path = manager.case_dir(resolved_case_id)
    if not case_path.exists():
        err_console.print(f"❌ case 디렉토리를 찾을 수 없습니다: {case_path}")
        raise typer.Exit(1)
    return case_path


def _print_json(payload: dict[str, Any]) -> None:
    """Render structured CLI output as JSON."""
    console.print(json.dumps(payload, ensure_ascii=False, indent=2))


@app.command()
def run(
    image_paths: list[Path] = typer.Argument(  # noqa: B008
        ...,
        help="입력 디자인 이미지 경로 (1개 이상)",
    ),
    prompt: str = typer.Option(..., "--prompt", help="생성 지시 프롬프트"),
    repo: Path = typer.Option(Path("."), "--repo", help="대상 레포 루트"),  # noqa: B008
    case_id: str | None = typer.Option(None, "--case-id", help="명시적 case ID"),
    as_json: bool = typer.Option(False, "--json", help="JSON으로 출력"),
) -> None:
    """디자인 이미지와 프롬프트로 전체 delivery pipeline을 실행합니다."""
    cfg = _state.config or DdalggakConfig()
    repo_path = repo.resolve()
    manager = WorkspaceManager(repo_path)
    manager.init()

    resolved_case_id = case_id or manager.next_case_id()
    case_path = manager.init_case(resolved_case_id)
    case_input = CaseInput(
        case_id=resolved_case_id,
        image_paths=[image.resolve() for image in image_paths],
        prompt=prompt,
        repo_path=repo_path,
    )

    runner = PipelineRunner(_build_runtime_services(cfg))
    final_state = asyncio.run(runner.run_case(case_input))

    store = CaseArtifactStore(case_path)
    store.persist(case_input, final_state)
    summary = store.load_status()

    if as_json:
        _print_json(summary)
    else:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"case_id: {summary['case_id']}",
                        f"decision: {summary['release_decision']}",
                        f"terminal_state: {summary['terminal_state']}",
                        f"score: {summary['scorecard_overall']}",
                        f"reports: {case_path / 'reports'}",
                    ]
                ),
                title="ddk run",
                expand=False,
            )
        )

    if summary["release_decision"] != "ready":
        raise typer.Exit(1)


@app.command()
def status(
    case_id: str | None = typer.Option(None, "--case-id", help="조회할 case ID"),
    repo: Path = typer.Option(Path("."), "--repo", help="대상 레포 루트"),  # noqa: B008
    as_json: bool = typer.Option(False, "--json", help="JSON으로 출력"),
) -> None:
    """저장된 case 상태를 조회합니다."""
    store = CaseArtifactStore(_resolve_case_path(repo, case_id))
    summary = store.load_status()
    if as_json:
        _print_json(summary)
    else:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"case_id: {summary['case_id']}",
                        f"decision: {summary['release_decision']}",
                        f"terminal_state: {summary['terminal_state']}",
                        f"current_node: {summary['current_node']}",
                        f"fix_attempts: {summary['fix_attempts']}",
                    ]
                ),
                title="ddk status",
                expand=False,
            )
        )
    if summary["release_decision"] != "ready":
        raise typer.Exit(1)


@app.command()
def certify(
    case_id: str | None = typer.Option(None, "--case-id", help="조회할 case ID"),
    repo: Path = typer.Option(Path("."), "--repo", help="대상 레포 루트"),  # noqa: B008
    as_json: bool = typer.Option(False, "--json", help="JSON으로 출력"),
) -> None:
    """저장된 certification 결과를 조회합니다."""
    store = CaseArtifactStore(_resolve_case_path(repo, case_id))
    scorecard = store.load_scorecard()
    release_decision = store.load_release_decision()
    evidence_pack = store.load_evidence_pack()
    payload = {
        "case_id": release_decision.case_id,
        "decision": release_decision.decision,
        "scorecard": scorecard.model_dump(mode="json"),
        "evidence_pack": evidence_pack.model_dump(mode="json"),
    }
    if as_json:
        _print_json(payload)
    else:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"case_id: {release_decision.case_id}",
                        f"decision: {release_decision.decision}",
                        f"grade: {scorecard.grade}",
                        f"overall: {scorecard.overall}",
                        f"evidence_terminal_state: {evidence_pack.terminal_state}",
                    ]
                ),
                title="ddk certify",
                expand=False,
            )
        )
    if release_decision.decision != "ready":
        raise typer.Exit(1)


@app.command()
def rollback(
    attempt_number: int = typer.Option(..., "--attempt", min=1, help="복구할 fix attempt 번호"),
    case_id: str = typer.Option(..., "--case-id", help="복구할 case ID"),
    repo: Path = typer.Option(Path("."), "--repo", help="대상 레포 루트"),  # noqa: B008
    force: bool = typer.Option(False, "--force", help="미커밋 변경사항을 버리고 강제 롤백"),
) -> None:
    """지정한 case/attempt의 git checkpoint로 롤백합니다."""
    from .exceptions import DirtyWorkingTreeError  # noqa: PLC0415
    from .services.rollback_controller import RollbackController  # noqa: PLC0415

    controller = RollbackController(git=LocalGitAdapter(), repo_path=repo.resolve())
    try:
        asyncio.run(
            controller.rollback_to_latest(
                case_id=case_id, attempt_number=attempt_number, force=force
            )
        )
    except DirtyWorkingTreeError as exc:
        err_console.print(f"❌ rollback 실패: 미커밋 변경사항이 있습니다 — {exc}")
        err_console.print("   --force 플래그를 사용하면 변경사항을 버리고 강제 롤백합니다.")
        raise typer.Exit(1) from exc
    except ValueError as exc:
        err_console.print(f"❌ rollback 실패: {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]✅ rollback 완료[/green] {case_id} attempt-{attempt_number}")


# ---------------------------------------------------------------------------
# ddk serve
# ---------------------------------------------------------------------------


@app.command()
def serve() -> None:
    """MCP 서버를 stdio 모드로 시작 (Claude Code, Cursor 등 자동 호출).

    설정 파일에 등록하면 AI 도구가 자동으로 시작합니다:
        ~/.claude/settings.json mcpServers.ddk.command = "ddk"
        ~/.claude/settings.json mcpServers.ddk.args    = ["serve"]
    """
    from .server import run_server  # noqa: PLC0415

    run_server()


# ---------------------------------------------------------------------------
# ddk install
# ---------------------------------------------------------------------------


@app.command()
def install(
    claude: bool = typer.Option(False, "--claude", help="Claude Code에 설치"),
    gemini: bool = typer.Option(False, "--gemini", help="Gemini CLI에 설치"),
    opencode: bool = typer.Option(False, "--opencode", help="OpenCode에 설치"),
    codex: bool = typer.Option(False, "--codex", help="OpenAI Codex CLI에 설치"),
    copilot: bool = typer.Option(False, "--copilot", help="GitHub Copilot에 설치"),
    cursor: bool = typer.Option(False, "--cursor", help="Cursor에 설치"),
    kiro: bool = typer.Option(False, "--kiro", help="Kiro에 설치"),
    all_tools: bool = typer.Option(False, "--all", "-a", help="감지된 모든 도구에 설치"),
    project: bool = typer.Option(  # noqa: B008
        True,
        "--project/--global",
        help="프로젝트 로컬 설치 (기본) vs 홈 디렉토리 전역 설치",
    ),
    detect: bool = typer.Option(False, "--detect", help="설치 없이 감지된 도구만 출력"),
) -> None:
    """AI 코딩 도구에 /ddk:design 슬래시 커맨드와 MCP 서버를 등록.

    예시:
        ddk install --all          # 감지된 모든 도구
        ddk install --claude       # Claude Code만
        ddk install --detect       # 어떤 도구가 있는지만 확인
    """
    from .installer import INSTALLERS, detect_tools  # noqa: PLC0415

    target = None if project else Path.home()

    if detect:
        found = detect_tools()
        if found:
            console.print("[bold]감지된 AI 도구:[/bold]")
            for t in found:
                console.print(f"  ✅ {t}")
        else:
            console.print("[yellow]감지된 AI 도구 없음[/yellow]")
        return

    # 설치 대상 결정
    selected: list[str] = []
    flags = {
        "claude": claude,
        "gemini": gemini,
        "opencode": opencode,
        "codex": codex,
        "copilot": copilot,
        "cursor": cursor,
        "kiro": kiro,
    }

    if all_tools:
        selected = list(INSTALLERS.keys())
    else:
        selected = [name for name, flag in flags.items() if flag]

    if not selected:
        console.print("[yellow]설치할 도구를 지정하세요. 예: ddk install --all[/yellow]")
        console.print("  감지 먼저: ddk install --detect")
        raise typer.Exit(1)

    console.print(f"[bold cyan]DDK 설치[/bold cyan] → {', '.join(selected)}\n")

    success_count = 0
    for tool_name in selected:
        fn = INSTALLERS.get(tool_name)
        if fn is None:
            continue
        try:
            result = fn(target)
            icon = "✅" if result.success else "❌"
            console.print(f"  {icon} [bold]{result.tool}[/bold]: {result.message}")
            for f in result.installed_files:
                console.print(f"       {f}")
            if result.success:
                success_count += 1
        except Exception as e:  # noqa: BLE001
            console.print(f"  ❌ [bold]{tool_name}[/bold]: {e}")

    console.print(f"\n[green]{success_count}/{len(selected)}개 도구 설치 완료[/green]")
    if success_count > 0:
        console.print("\n[bold]다음 단계:[/bold]")
        console.print("  1. AI 도구를 재시작하세요")
        console.print('  2. /ddk:design "쇼핑몰" 명령을 실행하세요')


# ---------------------------------------------------------------------------
# ddk doctor
# ---------------------------------------------------------------------------


@app.command()
def doctor() -> None:
    """환경 점검 — Python, uv, API 키, Node.js, git 버전 확인."""
    from .preflight.doctor import PreflightDoctor  # noqa: PLC0415

    results = PreflightDoctor().run_checks()
    has_critical_fail = False

    for r in results:
        if r["status"] == "pass":
            icon = "✅"
        elif r["status"] == "warn":
            icon = "⚠️ "
        else:
            icon = "❌"
            if r["critical"]:
                has_critical_fail = True

        console.print(f"  {icon} {r['name']}: {r['detail']}")

    if has_critical_fail:
        console.print("\n[red]❌ 필수 환경 설정이 누락됐습니다.[/red]")
        raise typer.Exit(1)

    console.print("\n[green]✅ 모든 검사 통과.[/green]")


# ---------------------------------------------------------------------------
# ddk init
# ---------------------------------------------------------------------------


@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="프로젝트 루트 경로"),  # noqa: B008
) -> None:
    """.ddk/ 워크스페이스 디렉토리를 초기화합니다 (이미 있으면 안전하게 건너뜀)."""
    from .workspace.manager import WorkspaceManager  # noqa: PLC0415

    manager = WorkspaceManager(path.resolve())
    manager.init()
    console.print(f"[green]✅ .ddk/ 초기화 완료:[/green] {manager.root}")


def cli_main() -> None:
    """CLI 진입점."""
    app()

"""Workspace and environment commands: version, init, doctor, preflight, install, serve."""

from __future__ import annotations

from pathlib import Path

import typer

from ddk.adapters.browser_install import install_chromium
from ddk.i18n import t
from ddk.workspace.manager import WorkspaceManager

from .app import app
from .common import console, err_console, get_config, state


@app.command()
def version() -> None:
    """Print the installed ddalggak version."""
    try:
        from importlib.metadata import version as pkg_version  # noqa: PLC0415

        ver = pkg_version("ddalggak")
    except Exception:  # noqa: BLE001
        ver = "0.0.0-dev"
    console.print(f"ddk {ver}")


@app.command(help=t("환경 점검 — API 키, Python 버전, 의존성 확인."))
def preflight() -> None:
    """Check the API key, the Python version and the dependencies."""
    cfg = get_config()
    checks: list[tuple[str, bool, str]] = []

    import sys as _sys  # noqa: PLC0415

    py_ok = _sys.version_info >= (3, 12)
    checks.append(("Python >= 3.12", py_ok, f"Python {_sys.version.split()[0]}"))

    provider_ok = cfg.llm_provider == "anthropic"
    provider_detail = "anthropic" if provider_ok else f"unsupported: {cfg.llm_provider}"
    checks.append(("LLM provider", provider_ok, provider_detail))

    api_ok = provider_ok and bool(cfg.anthropic_api_key)
    checks.append(("LLM API key", api_ok, "set" if api_ok else "missing"))

    sandbox_ok = cfg.sandbox_mode == "tempdir"
    sandbox_detail = "tempdir" if sandbox_ok else f"unsupported: {cfg.sandbox_mode}"
    checks.append(("Sandbox mode", sandbox_ok, sandbox_detail))

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


@app.command(help=t("환경 점검 — Python, uv, API 키, Node.js, git, 헤드리스 Chromium 확인."))
def doctor(
    install_browser: bool = typer.Option(
        False,
        "--install-browser",
        help=t("먼저 헤드리스 Chromium 을 내려받습니다 (Playwright 사용, 한 번만)"),
    ),
) -> None:
    """Check every tool the loop needs and say which ones are optional."""
    from ddk.preflight.doctor import PreflightDoctor  # noqa: PLC0415

    if install_browser:
        console.print(t("Chromium 을 내려받는 중입니다…"))
        if not install_chromium():
            err_console.print(
                t("❌ Chromium 을 내려받지 못했습니다. 네트워크를 확인하거나 Chrome 을 설치하세요.")
            )
            raise typer.Exit(1)

    results = PreflightDoctor(state.config).run_checks()
    has_critical_fail = False

    if state.config_error is not None:
        console.print(
            t("  ❌ 설정 값: 환경 변수나 .env 의 값이 올바르지 않습니다 (ddk run 에서 자세히 표시)")
        )
        has_critical_fail = True

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
        console.print(t("\n[red]❌ 필수 환경 설정이 누락됐습니다.[/red]"))
        raise typer.Exit(1)

    console.print(t("\n[green]✅ 모든 검사 통과.[/green]"))


@app.command(help=t(".ddk/ 작업 폴더를 초기화합니다 (이미 있으면 안전하게 건너뜀)."))
def init(
    path: Path = typer.Argument(Path("."), help=t("프로젝트 루트 경로")),
) -> None:
    """Create the .ddk/ folder; an existing one is left alone."""
    manager = WorkspaceManager(path.resolve())
    manager.init()
    console.print(t("[green]✅ .ddk/ 초기화 완료:[/green] {path}", path=manager.root))


@app.command(
    help=t("MCP 서버를 stdio 방식으로 시작합니다 (Claude Code, Cursor 등이 호출)."),
    epilog=t("AI 도구에 등록하려면: ddk install --all"),
)
def serve() -> None:
    """Start the MCP server on stdio."""
    from ddk.server import run_server  # noqa: PLC0415

    run_server()


@app.command(
    help=t("AI 코딩 도구에 /ddk:design 명령과 MCP 서버를 등록합니다."),
    epilog=t("예시: ddk install --detect · ddk install --claude · ddk install --all"),
)
def install(
    claude: bool = typer.Option(False, "--claude", help=t("Claude Code에 설치")),
    gemini: bool = typer.Option(False, "--gemini", help=t("Gemini CLI에 설치")),
    opencode: bool = typer.Option(False, "--opencode", help=t("OpenCode에 설치")),
    codex: bool = typer.Option(False, "--codex", help=t("OpenAI Codex CLI에 설치")),
    copilot: bool = typer.Option(False, "--copilot", help=t("GitHub Copilot에 설치")),
    cursor: bool = typer.Option(False, "--cursor", help=t("Cursor에 설치")),
    kiro: bool = typer.Option(False, "--kiro", help=t("Kiro에 설치")),
    all_tools: bool = typer.Option(False, "--all", "-a", help=t("감지된 모든 도구에 설치")),
    project: bool = typer.Option(
        True,
        "--project/--global",
        help=t("프로젝트 로컬 설치 (기본) vs 홈 폴더 전역 설치"),
    ),
    detect: bool = typer.Option(False, "--detect", help=t("설치 없이 감지된 도구만 출력")),
) -> None:
    """Register the /ddk:design command and the MCP server with AI coding tools."""
    from ddk.installer import INSTALLERS, detect_tools  # noqa: PLC0415

    target = None if project else Path.home()

    if detect:
        found = detect_tools()
        if found:
            console.print(t("[bold]감지된 AI 도구:[/bold]"))
            for tool in found:
                console.print(f"  ✅ {tool}")
        else:
            console.print(t("[yellow]감지된 AI 도구 없음[/yellow]"))
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
        console.print(t("[yellow]설치할 도구를 지정하세요. 예: ddk install --all[/yellow]"))
        console.print(t("  감지 먼저: ddk install --detect"))
        raise typer.Exit(1)

    console.print(t("[bold cyan]DDK 설치[/bold cyan] → {tools}\n", tools=", ".join(selected)))

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

    console.print(
        t(
            "\n[green]{done}/{total}개 도구 설치 완료[/green]",
            done=success_count,
            total=len(selected),
        )
    )
    if success_count > 0:
        console.print(t("\n[bold]다음 단계:[/bold]"))
        console.print(t("  1. AI 도구를 재시작하세요"))
        console.print(t('  2. /ddk:design "쇼핑몰" 명령을 실행하세요'))

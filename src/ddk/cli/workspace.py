"""Workspace and environment commands: version, init, doctor, preflight, install, serve."""

from __future__ import annotations

from pathlib import Path

import typer

from ddk.adapters.browser_install import install_chromium
from ddk.i18n import t
from ddk.workspace.manager import WorkspaceManager

from .app import app
from .common import console, err_console, get_config


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
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json"),
    repo: Path = typer.Option(Path("."), "--repo"),
    install_browser: bool = typer.Option(
        False,
        "--install-browser",
        help=t("먼저 헤드리스 Chromium 을 내려받습니다 (Playwright 사용, 한 번만)"),
    ),
) -> None:
    """Inspect one readiness contract; dry-run always excludes installation."""
    import asyncio

    from rich.table import Table

    from ddk.services.verified_host import readiness

    from .verified import emit_result, execute_command

    if install_browser and not dry_run:
        err_console.print(t("Chromium 을 내려받는 중입니다…"))
        if not install_chromium():
            err_console.print(
                t("❌ Chromium 을 내려받지 못했습니다. 네트워크를 확인하거나 Chrome 을 설치하세요.")
            )
            raise typer.Exit(1)

    if as_json:
        execute_command(True, lambda: asyncio.run(readiness(repo)))
        return

    result = asyncio.run(readiness(repo))
    emit_result(result, False)
    table = Table("Check", "Status", "Action")
    names = {"python": "Python", "chromium": "Headless Chromium", "settings": t("설정 값")}
    icons = {"ready": "✅", "warning": "⚠️", "blocked": "❌"}
    for row in result["checks"]:
        table.add_row(
            f"{icons[row['status']]} {names.get(row['name'], row['name'])}",
            row["status"],
            row["action"] or "",
        )
    console.print(table)
    if result["status"] == "blocked":
        raise typer.Exit(2)


@app.command(
    "workspace-init", help=t(".ddk/ 작업 폴더를 초기화합니다 (이미 있으면 안전하게 건너뜀).")
)
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


@app.command(help=t("AI 도구에 DDK 스킬과 MCP 설정을 설치합니다."))
def install(
    claude: bool = typer.Option(False, "--claude"),
    gemini: bool = typer.Option(False, "--gemini"),
    opencode: bool = typer.Option(False, "--opencode"),
    codex: bool = typer.Option(False, "--codex"),
    copilot: bool = typer.Option(False, "--copilot"),
    cursor: bool = typer.Option(False, "--cursor"),
    kiro: bool = typer.Option(False, "--kiro"),
    host: str | None = typer.Option(None, "--host"),
    all_tools: bool = typer.Option(False, "--all", "-a", help=t("감지된 모든 도구에 설치")),
    project: bool = typer.Option(True, "--project/--global"),
    detect: bool = typer.Option(False, "--detect"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json"),
    with_hooks: bool = typer.Option(False, "--with-hooks"),
) -> None:
    from ddk.installer import HOSTS, detect_tools, install_host, install_plan

    from .common import print_json
    from .contract import envelope

    target = Path.cwd() if project else Path.home()
    flags = {
        "claude": claude,
        "gemini": gemini,
        "opencode": opencode,
        "codex": codex,
        "copilot": copilot,
        "cursor": cursor,
        "kiro": kiro,
    }
    selected = (
        detect_tools() if all_tools or detect else [name for name, flag in flags.items() if flag]
    )
    if host:
        if host not in HOSTS:
            raise typer.BadParameter("unknown host", param_hint="--host")
        selected = list(dict.fromkeys([*selected, host]))
    if with_hooks and not project:
        raise typer.BadParameter("--with-hooks requires a project installation")
    if not selected and not detect:
        if as_json:
            print_json(
                envelope(
                    "install",
                    {},
                    status="blocked",
                    code="host_required",
                    message="Select a host or detect installed tools.",
                )
            )
        else:
            console.print(t("[yellow]설치할 도구를 지정하세요. 예: ddk install --all[/yellow]"))
        raise typer.Exit(1)
    plans: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    for name in selected:
        try:
            plan = install_plan(name, target, global_scope=not project)
            if not dry_run and not detect:
                if with_hooks:
                    from ddk.installer import prepare_hooks

                    prepare_hooks(target)
                install_host(name, target, global_scope=not project)
            plans.append(plan)
        except (OSError, ValueError) as exc:
            failures.append({"host": name, "code": str(exc)})
    if with_hooks and not dry_run and not detect and not failures:
        from ddk.installer import install_hooks

        install_hooks(target)
    data = {"hosts": plans, "failures": failures, "dry_run": dry_run, "detect": detect}
    if as_json:
        print_json(envelope("install", data, status="blocked" if failures else "ok"))
    else:
        for name in selected:
            console.print(name)
        for failure in failures:
            err_console.print(str(failure))
    if failures:
        raise typer.Exit(3)


@app.command(help=t("설치 기록과 해시가 일치하는 DDK 파일을 제거합니다."))
def uninstall(
    host: str | None = typer.Option(None, "--host"),
    all_tools: bool = typer.Option(False, "--all"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    as_json: bool = typer.Option(False, "--json"),
    project: bool = typer.Option(True, "--project/--global"),
) -> None:
    from ddk.installer import HOSTS, uninstall_hosts

    from .common import print_json
    from .contract import envelope

    if (host is None) == (not all_tools) or (host is not None and host not in HOSTS):
        raise typer.BadParameter("select --host NAME or --all")
    try:
        result = uninstall_hosts(
            list(HOSTS) if all_tools else [host or ""],
            Path.cwd() if project else Path.home(),
            dry_run=dry_run,
        )
    except (ValueError, OSError) as exc:
        if as_json:
            print_json(
                envelope(
                    "uninstall",
                    {},
                    status="error",
                    code="invalid_install_manifest",
                    message=str(exc),
                )
            )
        else:
            err_console.print(str(exc))
        raise typer.Exit(3) from exc
    if as_json:
        print_json(envelope("uninstall", result, status=str(result["status"])))
    else:
        console.print(result)
    if result["status"] == "blocked":
        raise typer.Exit(1)

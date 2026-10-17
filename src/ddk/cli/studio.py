"""``ddk design new`` — an idea becomes ten design documents."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Prompt

from ddk.i18n import t
from ddk.models.config import DdalggakConfig

from .app import design_app
from .common import console, get_config, require_api_key


@design_app.command(
    "new",
    help=t("아이디어 → 인터뷰 → 10개 설계 문서 자동 생성."),
    epilog=t('예시: ddk design new "AI 기반 코드 리뷰 도구" -y'),
)
def design_new(
    idea: str = typer.Argument(..., help=t("프로젝트 아이디어 (자유 텍스트)")),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", "-y", help=t("인터뷰 없이 바로 생성")
    ),
    output: Path = typer.Option(Path("."), "-o", "--output", help=t("출력 폴더")),
) -> None:
    """Interview the user about an idea, then write the design documents."""
    cfg = get_config()
    out_dir = output

    require_api_key(cfg)

    asyncio.run(_run_design_new(idea, cfg, out_dir, non_interactive))


async def _run_design_new(
    idea: str,
    cfg: DdalggakConfig,
    out_dir: Path,
    non_interactive: bool,
) -> None:
    from ddk.adapters.llm.claude import ClaudeAdapter  # noqa: PLC0415
    from ddk.design import DesignGenerator, DesignInterviewer, DesignWriter  # noqa: PLC0415

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
        from ddk.design.interviewer import InterviewResult  # noqa: PLC0415

        interview_result = InterviewResult(
            project_name=idea[:50],
            original_idea=idea,
        )
    else:
        console.print(t("\n[bold]Step 1/2:[/bold] 요구사항 인터뷰\n"))
        interviewer = DesignInterviewer(llm=llm, model=cfg.llm_model)

        def ask_fn(question: str) -> str:
            return Prompt.ask(f"\n[cyan]{question}[/cyan]")

        interview_result = await interviewer.run(idea=idea, ask_fn=ask_fn)
        console.print(
            t(
                "\n[green]인터뷰 완료[/green] — {questions}개 질문, "
                "{requirements}개 요구사항 도출\n",
                questions=len(interview_result.turns),
                requirements=len(interview_result.extracted_requirements),
            )
        )

    # Phase 2: Generate 10 documents
    console.print(t("[bold]Step 2/2:[/bold] 설계 문서 생성 (10개)\n"))

    from ddk.design.templates import TEMPLATES  # noqa: PLC0415

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

    console.print(t("\n[bold green]✅ 완료![/bold green]"))
    warn = t(" ⚠️ {count}개 실패", count=err_count) if err_count else ""
    console.print(t("   문서: {count}개 생성{warn}", count=doc_count, warn=warn))
    console.print(t("   비용: ${cost:.4f} USD", cost=cost))
    console.print(t("   위치: [cyan]{path}[/cyan]", path=pkg_dir))

    if err_count:
        console.print(
            t(
                "\n[yellow]실패한 문서:[/yellow] {names}",
                names=", ".join(gen_result.errors.keys()),
            )
        )
        console.print(t("  자세한 내용: design-package/ERRORS.md"))

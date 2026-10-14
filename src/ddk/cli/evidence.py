"""Evidence commands: the claim gate (proof) and the standards map (audit)."""

from __future__ import annotations

import webbrowser
from pathlib import Path

import typer
from rich.panel import Panel
from rich.table import Table

from ddk.i18n import t
from ddk.services.case_report import ReportUnavailableError, write_report

from .app import app
from .common import console, err_console, print_json, resolve_case_path


@app.command(help=t("저장된 case의 증거 보고서(HTML 한 장)를 만듭니다."))
def report(
    case_id: str | None = typer.Option(None, "--case-id", help=t("대상 case ID (기본: 가장 최근)")),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    output: Path | None = typer.Option(
        None, "--output", "-o", help=t("저장할 파일 (기본: case 폴더의 reports/report.html)")
    ),
    open_page: bool = typer.Option(False, "--open", help=t("만든 뒤 기본 브라우저로 엽니다")),
) -> None:
    """Write the evidence page of a saved case."""
    case_path = resolve_case_path(repo, case_id)
    try:
        page = write_report(case_path, output)
    except ReportUnavailableError as exc:
        err_console.print(str(exc), markup=False, soft_wrap=True)
        raise typer.Exit(1) from exc
    except OSError as exc:
        err_console.print(t("❌ 보고서를 쓸 수 없습니다: {error}", error=exc), markup=False)
        raise typer.Exit(1) from exc
    console.print(t("✅ 보고서 작성: {path}", path=page), markup=False, soft_wrap=True)
    if open_page:
        webbrowser.open(page.resolve().as_uri())


@app.command(
    help=t(
        "기능 대응표를 실제 증거 파일로 검증하고, 주장해도 되는 항목만 출력합니다. "
        "증거가 디스크에 있고 관문 조건을 채울 때만 allowed 로 표시됩니다."
    )
)
def proof(
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
    strict: bool = typer.Option(
        False, "--strict", help=t("superset claim이 허용되지 않으면 비정상 종료(코드 1)")
    ),
) -> None:
    """Verify the capability matrix against the evidence on disk and print the allowed claims."""
    from ddk.services.proof_ledger import MatrixLoadError, ProofLedger  # noqa: PLC0415

    try:
        report = ProofLedger(repo.resolve()).verify()
    except MatrixLoadError as exc:
        console.print(t("[red]❌ capability matrix 로드 실패:[/red] {error}", error=exc))
        raise typer.Exit(2) from exc

    if as_json:
        print_json(report.model_dump(mode="json"))
        if strict and "superset" not in report.allowed_claims:
            raise typer.Exit(1)
        return

    fam_table = Table(title="Capability Matrix (artifact-resolved)", expand=False)
    fam_table.add_column("family")
    fam_table.add_column("class")
    fam_table.add_column("state")
    state_color = {
        "proved": "green",
        "mapped": "cyan",
        "partial": "yellow",
        "pending": "red",
    }
    for fam in report.families:
        color = state_color[fam.state]
        fam_table.add_row(fam.id, fam.classification, f"[{color}]{fam.state}[/{color}]")
    console.print(fam_table)

    claim_table = Table(title="Claim Gate", expand=False)
    claim_table.add_column("claim")
    claim_table.add_column("subject")
    claim_table.add_column("verdict")
    claim_table.add_column("reason")
    for claim in report.claims:
        verdict = "[green]ALLOWED[/green]" if claim.allowed else "[red]DENIED[/red]"
        reason = "; ".join(claim.satisfied if claim.allowed else claim.unmet) or "—"
        if len(reason) > 70:
            reason = reason[:67] + "…"
        claim_table.add_row(claim.claim_type, claim.subject or "—", verdict, reason)
    console.print(claim_table)

    console.print(
        Panel(report.summary, title=f"ddk proof · maturity {report.maturity_level}", expand=False)
    )

    if strict and "superset" not in report.allowed_claims:
        raise typer.Exit(1)


@app.command(
    help=t("국제표준 조항 → 산출물 대응 범위를 검증합니다 (인증이 아니라 대응 범위 확인).")
)
def audit(
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
    write: bool = typer.Option(False, "--write", help=t("benchmarks/compliance-matrix.json 생성")),
    strict: bool = typer.Option(False, "--strict", help=t("gap이 있으면 비정상 종료(코드 1)")),
) -> None:
    """Check which clauses of the listed standards map to an artifact."""
    from ddk.services.compliance_auditor import CatalogLoadError, ComplianceAuditor  # noqa: PLC0415

    auditor = ComplianceAuditor(repo.resolve())
    try:
        report = auditor.audit()
    except CatalogLoadError as exc:
        console.print(t("[red]❌ 표준 목록 로드 실패:[/red] {error}", error=exc))
        raise typer.Exit(2) from exc

    if write:
        out = auditor.write_matrix(report)
        console.print(t("[green]✅ 대응표 작성:[/green] {path}", path=out))

    if as_json:
        print_json(report.model_dump(mode="json"))
        if strict and report.gaps:
            raise typer.Exit(1)
        return

    table = Table(title="Standards Mapping (clause → artifact coverage)", expand=False)
    table.add_column("standard")
    table.add_column("clause")
    table.add_column("status")
    color_of = {"mapped": "green", "partial": "yellow", "gap": "red"}
    for clause in report.clauses:
        color = color_of[clause.status]
        table.add_row(clause.standard, clause.clause, f"[{color}]{clause.status}[/{color}]")
    console.print(table)
    console.print(
        Panel(
            report.summary
            + t(
                "\n[dim]coverage = clauses fully mapped / total · "
                "인증이 아니라 조항 대응 범위입니다.[/dim]"
            ),
            title="ddk audit",
            expand=False,
        )
    )

    if strict and report.gaps:
        raise typer.Exit(1)

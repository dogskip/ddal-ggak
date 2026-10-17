"""Local numeric reports require neither a provider nor network transmission."""

from pathlib import Path

import typer

from ddk.i18n import t
from ddk.services.local_stats import summarize_costs

from .app import app
from .common import console, print_json
from .contract import CommandFailureError


@app.command(help=t("로컬 비용 기록을 원문 없이 집계합니다."))
def stats(
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    try:
        result = summarize_costs(repo)
    except (ValueError, OSError) as error:
        raise CommandFailureError("integrity", "invalid_cost_records") from error
    if as_json:
        print_json(result)
    else:
        console.print(result)
    if not result["complete"]:
        raise typer.Exit(1)


@app.command(help=t("같은 조건의 비교 기록을 검증합니다. 모델은 호출하지 않습니다."))
def bench(
    receipts: Path | None = typer.Option(None, "--receipts", help=t("비교 기록 JSON 파일")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    from ddk.services.paired_benchmark import summarize_pairs

    try:
        result = summarize_pairs(receipts)
    except (ValueError, OSError) as error:
        raise CommandFailureError("integrity", "invalid_comparison_records") from error
    if as_json:
        print_json(result)
    else:
        console.print(result)
    if result["status"] in {"unmeasured", "incomplete"}:
        raise typer.Exit(1)

"""``ddk demo`` — the whole loop on a built-in page, with no API key."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel

from ddk.adapters.browser_install import install_chromium
from ddk.demo.runner import (
    DemoResult,
    DemoUnavailableError,
    check_prerequisites,
    real_services,
    run_demo,
)
from ddk.i18n import t
from ddk.services.progress import describe_stage

from .app import app
from .common import console, err_console, get_config, is_interactive


@app.command(
    help=t("API 키 없이 전체 절차를 체험합니다: 디자인 → 코드 → 화면 비교 → 자동 수정 → 판정.")
)
def demo(
    workdir: Path | None = typer.Option(
        None, "--workdir", help=t("결과를 보관할 새 폴더 (기본: 임시 폴더)")
    ),
) -> None:
    """Run the whole loop on the built-in page, without an API key."""
    problems = check_prerequisites(install_browser=_offer_browser_download)
    if problems:
        for problem in problems:
            err_console.print(f"❌ {problem}")
        raise typer.Exit(1)

    target = workdir.resolve() if workdir else Path(tempfile.mkdtemp(prefix="ddk-demo-"))
    console.print(
        t(
            "ddk demo — 모델 응답은 미리 녹화한 것을 재생하고, 빌드·브라우저·화면 비교는 "
            "실제로 실행합니다 (API 키 불필요)."
        )
    )
    console.print(t("작업 폴더: {path}", path=target), markup=False, soft_wrap=True)
    console.print(t("프로젝트 복사와 의존성 설치(npm ci)로 시작합니다…"))

    def show_stage(stage: str, update: dict[str, Any]) -> None:
        console.print(f"  • {describe_stage(stage, update)}", markup=False, highlight=False)

    cfg = get_config()
    services = real_services(cfg.chromium_path or None)
    try:
        result = asyncio.run(run_demo(target, services=services, on_update=show_stage))
    except DemoUnavailableError as exc:
        err_console.print(f"❌ {exc}")
        raise typer.Exit(1) from exc
    _print_demo_summary(result)
    if result.summary["release_decision"] != "ready":
        raise typer.Exit(1)


def _offer_browser_download() -> bool:
    """With no Chromium at all, the first run offers the one-time download instead of stopping."""
    if not is_interactive():
        return False
    question = t("헤드리스 Chromium 이 없습니다. 지금 내려받을까요? (한 번만, 디스크 약 200MB)")
    if not typer.confirm(question, default=True):
        return False
    console.print(t("Chromium 을 내려받는 중입니다…"))
    return install_chromium()


def _print_demo_summary(result: DemoResult) -> None:
    final = result.final_state.get("visual_regression_report")
    lines: list[str] = []
    first = result.first_attempt
    if first is not None:
        lines.append(
            t(
                "첫 시도: SSIM {ssim:.2f}, 디자인과 크게 다른 면적 {mismatch:.1%}"
                " → 화면 비교에서 걸림",
                ssim=first.ssim,
                mismatch=first.mismatch_ratio,
            )
        )
    if final is not None:
        lines.append(
            t(
                "자동 수정 {attempts}회 뒤: SSIM {ssim:.2f}",
                attempts=result.summary["fix_attempts"],
                ssim=final.ssim_score,
            )
        )
    lines.append(t("판정: {decision}", decision=result.summary["release_decision"]))
    console.print(Panel("\n".join(lines), title="ddk demo", expand=False))

    root = result.project_path.parent
    case = result.case_path.relative_to(root)
    files: list[tuple[str, Path]] = []
    if result.report_path is not None:
        files.append((t("증거 보고서"), result.report_path.relative_to(root)))
    files.append((t("디자인(와이어프레임)"), result.design_path.relative_to(root)))
    if first is not None:
        files.append((t("첫 시도 화면"), first.screenshot.relative_to(root)))
        files.append((t("차이 표시(빨강)"), first.diff.relative_to(root)))
    files.append((t("수정 뒤 화면"), case / "artifacts" / "visual" / "generated.png"))
    files.append((t("생성된 코드"), case / "artifacts" / "generated"))
    console.print(t("파일 (작업 폴더 기준):"))
    for label, path in files:
        console.print(f"  {label}: {path}", markup=False, soft_wrap=True)
    console.print(t("\n내 디자인으로: ddk run <이미지> (ANTHROPIC_API_KEY 필요)"))

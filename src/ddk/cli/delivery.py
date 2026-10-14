"""The delivery loop: run a case, look at its result, apply it, roll it back."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from ddk.adapters.chromium_browser import BrowserUnavailableError
from ddk.i18n import t
from ddk.models.input import CaseInput
from ddk.services.artifact_applier import ArtifactApplier, FileChange
from ddk.services.case_artifact_store import CaseArtifactStore
from ddk.services.case_report import ReportUnavailableError, write_report
from ddk.services.images import is_decodable
from ddk.services.pipeline_runner import PipelineRunner, RuntimeServices
from ddk.services.progress import describe_stage
from ddk.workspace.manager import WorkspaceManager

from .app import app
from .common import (
    console,
    err_console,
    get_config,
    print_json,
    resolve_case_path,
    status_console,
)
from .runtime import build_runtime_services

# Sent to the model when ``ddk run`` gets an image and no instruction.
DEFAULT_PROMPT = (
    "Implement the attached design as a responsive web page that follows the repository's "
    "existing framework, conventions and styling. Match the layout, spacing, typography "
    "and colours of the image as closely as possible."
)


@app.command(help=t("디자인 이미지와 프롬프트로 전체 절차를 실행합니다."))
def run(
    image_paths: list[Path] = typer.Argument(
        ...,
        help=t("입력 디자인 이미지 경로 (1개 이상)"),
    ),
    prompt: str = typer.Option(
        DEFAULT_PROMPT,
        "--prompt",
        "-p",
        show_default=False,
        help=t("생성 지시 프롬프트 (생략하면 이미지를 그대로 구현)"),
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    case_id: str | None = typer.Option(None, "--case-id", help=t("명시적 case ID")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
    install: bool = typer.Option(
        False,
        "--install",
        help=t("일시 사본에 의존성 설치 (--ignore-scripts); 원본 의존성은 복사하지 않습니다"),
    ),
    visual: bool | None = typer.Option(
        None,
        "--visual/--no-visual",
        help=t("렌더링 화면과 디자인 이미지 비교 (기본: 켜짐). --no-visual 은 비교를 면제합니다."),
    ),
    ssim_threshold: float | None = typer.Option(
        None,
        "--ssim-threshold",
        min=0.0,
        max=1.0,
        help=t("화면 유사도(SSIM) 통과 기준 (기본 0.92)"),
    ),
    max_mismatch: float | None = typer.Option(
        None,
        "--max-mismatch",
        min=0.0,
        max=1.0,
        help=t("디자인과 크게 다른 면적 비율의 허용 한도 (기본 0.03)"),
    ),
) -> None:
    """Run the whole delivery loop for one case."""
    cfg = get_config()
    overrides: dict[str, Any] = {}
    if install:
        overrides["install_dependencies"] = True
    if visual is not None:
        overrides["visual_check"] = visual
    if ssim_threshold is not None:
        overrides["ssim_threshold"] = ssim_threshold
    if max_mismatch is not None:
        overrides["max_mismatch_ratio"] = max_mismatch
    if overrides:
        cfg = cfg.model_copy(update=overrides)
    repo_path = repo.resolve()

    # Fail fast on bad preconditions BEFORE mutating the filesystem: validate the
    # provider + API key, then confirm every input image exists and decodes. A doomed run must
    # not leave an orphaned workspace/case directory behind.
    services = build_runtime_services(cfg)
    resolved_images = [image.resolve() for image in image_paths]
    missing_images = [str(p) for p in resolved_images if not p.is_file()]
    if missing_images:
        err_console.print(
            t("❌ 입력 이미지를 찾을 수 없습니다: {paths}", paths=", ".join(missing_images))
        )
        raise typer.Exit(1)
    broken_images = [str(p) for p in resolved_images if not is_decodable(p)]
    if broken_images:
        err_console.print(
            t("❌ 이미지로 읽을 수 없는 파일입니다: {paths}", paths=", ".join(broken_images))
        )
        raise typer.Exit(1)
    if cfg.visual_check:
        _require_browser(services)

    manager = WorkspaceManager(repo_path)
    manager.init()

    resolved_case_id = case_id or manager.next_case_id()
    case_path = manager.init_case(resolved_case_id)
    case_input = CaseInput(
        case_id=resolved_case_id,
        image_paths=resolved_images,
        prompt=prompt,
        repo_path=repo_path,
        visual_check=cfg.visual_check,
    )

    # Progress goes to stderr when the result is JSON on stdout.
    progress = status_console if as_json else console

    def show_stage(stage: str, update: dict[str, Any]) -> None:
        progress.print(f"  • {describe_stage(stage, update)}", markup=False, highlight=False)

    runner = PipelineRunner(services)
    final_state = asyncio.run(runner.run_case(case_input, case_dir=case_path, on_update=show_stage))

    store = CaseArtifactStore(case_path)
    store.persist(case_input, final_state)
    summary = store.load_status()
    report_path = _write_report_quietly(case_path)

    if as_json:
        if report_path is not None:
            summary["report"] = str(report_path)
        print_json(summary)
    else:
        console.print(
            Panel(
                "\n".join(
                    [
                        f"case_id: {summary['case_id']}",
                        f"decision: {summary['release_decision']}",
                        f"terminal_state: {summary['terminal_state']}",
                        f"score: {summary['scorecard_overall']}",
                        f"report: {report_path or case_path / 'reports'}",
                    ]
                ),
                title="ddk run",
                expand=False,
            )
        )

    if summary["release_decision"] != "ready":
        raise typer.Exit(1)


def _require_browser(services: RuntimeServices) -> None:
    """A run that must compare screenshots stops before it spends anything on a missing browser."""
    probe = getattr(services.browser, "probe", None)
    if probe is None:
        return
    try:
        asyncio.run(probe())
    except BrowserUnavailableError as exc:
        message = t("❌ 화면 비교에 사용할 브라우저를 시작할 수 없습니다: {error}", error=exc)
        err_console.print(message, markup=False, highlight=False, soft_wrap=True)
        err_console.print(
            t("   비교를 건너뛰려면 --no-visual 을 붙이세요 (건너뛴 사실은 보고서에 남습니다)."),
            soft_wrap=True,
        )
        raise typer.Exit(1) from exc


def _write_report_quietly(case_path: Path) -> Path | None:
    """The report is a convenience: a run never fails because it could not be written."""
    try:
        return write_report(case_path)
    except (ReportUnavailableError, OSError):
        return None


@app.command(help=t("저장된 case 상태를 조회합니다."))
def status(
    case_id: str | None = typer.Option(None, "--case-id", help=t("조회할 case ID")),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    """Show the saved state of a case."""
    store = CaseArtifactStore(resolve_case_path(repo, case_id))
    summary = store.load_status()
    if as_json:
        print_json(summary)
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


@app.command(help=t("저장된 판정 결과를 조회합니다."))
def certify(
    case_id: str | None = typer.Option(None, "--case-id", help=t("조회할 case ID")),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    """Show the saved verdict of a case."""
    store = CaseArtifactStore(resolve_case_path(repo, case_id))
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
        print_json(payload)
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


@app.command(help=t("검증을 통과한 case의 생성 파일을 저장소에 적용합니다."))
def apply(
    case_id: str | None = typer.Option(
        None, "--case-id", help=t("적용할 case ID (기본: 가장 최근)")
    ),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    dry_run: bool = typer.Option(
        False, "--dry-run", help=t("파일 변경 없이 반영 계획을 표시합니다")
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help=t("호환 옵션: 사용하면 내보내기 안내와 함께 중단합니다"),
    ),
    allow_blocked: bool = typer.Option(
        False, "--allow-blocked", help=t("호환 옵션: 사용하면 내보내기 안내와 함께 중단합니다")
    ),
    as_json: bool = typer.Option(False, "--json", help=t("JSON으로 출력")),
) -> None:
    """Write the files of a verified case into the repository."""
    if force or allow_blocked:
        err_console.print(t("❌ 강제 반영은 제공하지 않습니다. 내보내기 후 충돌을 해결하세요."))
        raise typer.Exit(2)
    case_path = resolve_case_path(repo, case_id)
    store = CaseArtifactStore(case_path)
    try:
        decision = store.load_release_decision()
        artifacts = store.load_generated_artifacts()
    except (OSError, ValueError) as exc:
        err_console.print(t("❌ case 결과를 읽을 수 없습니다: {error}", error=exc))
        raise typer.Exit(1) from exc
    if decision.decision != "ready":
        err_console.print(
            t(
                "❌ 판정이 ready가 아니라서 적용하지 않습니다 (현재: {decision}).",
                decision=decision.decision,
            )
        )
        err_console.print(t("   `ddk status`로 원인을 확인한 후 변경을 내보내세요."))
        raise typer.Exit(1)

    repo_path = repo.resolve()
    applier = ArtifactApplier()
    changes = applier.plan(artifacts, repo_path)
    rejected = [c for c in changes if c.action == "rejected"]
    conflicts = [c for c in changes if c.action == "conflict"]
    blocked = bool(rejected) or bool(conflicts)
    written: list[FileChange] = []
    if not dry_run and not blocked:
        written = applier.write(
            changes, repo_path, force=force, backup_dir=case_path / "artifacts" / "replaced"
        )

    if as_json:
        print_json(
            {
                "case_id": decision.case_id,
                "decision": decision.decision,
                "dry_run": dry_run,
                "files": [
                    {"path": c.path, "action": c.action, "reason": c.reason} for c in changes
                ],
                "written": [c.path for c in written],
            }
        )
    else:
        _print_changes(changes, dry_run=dry_run)
        if written:
            console.print(t("[green]✅ {count}개 파일을 적용했습니다[/green]", count=len(written)))
    if dry_run:
        return
    if rejected:
        err_console.print(t("❌ 쓸 수 없는 경로가 있어 아무것도 적용하지 않았습니다."))
        raise typer.Exit(1)
    if conflicts:
        err_console.print(t("❌ 실행 뒤에 바뀐 파일이 있어 아무것도 적용하지 않았습니다."))
        err_console.print(t("   변경을 내보낸 뒤 현재 파일과 충돌을 해결하세요."))
        raise typer.Exit(1)


def _print_changes(changes: list[FileChange], *, dry_run: bool) -> None:
    labels = {
        "create": t("새 파일"),
        "update": t("수정"),
        "unchanged": t("변경 없음"),
        "conflict": t("충돌"),
        "rejected": t("거부"),
    }
    table = Table(title=t("ddk apply (계획)") if dry_run else "ddk apply")
    table.add_column(t("파일"))
    table.add_column(t("작업"))
    table.add_column(t("비고"))
    for change in changes:
        table.add_row(change.path, labels[change.action], change.reason, style=None)
    console.print(table)


@app.command(help=t("이전 복구 명령의 중단 사유와 안전한 대안을 표시합니다."))
def rollback(
    attempt_number: int = typer.Option(..., "--attempt", min=1, help=t("복구할 fix attempt 번호")),
    case_id: str = typer.Option(..., "--case-id", help=t("복구할 case ID")),
    repo: Path = typer.Option(Path("."), "--repo", help=t("대상 저장소 폴더")),
    force: bool = typer.Option(
        False, "--force", help=t("호환 옵션: 사용하면 내보내기 안내와 함께 중단합니다")
    ),
) -> None:
    """Reject whole-repository resets and point to owned application recovery."""
    err_console.print(
        t("❌ Git 전체 초기화 복구는 제공하지 않습니다. 관리된 반영 기록으로 복구하세요.")
    )
    raise typer.Exit(2)

"""One readable line for each graph stage that finishes."""

from __future__ import annotations

from typing import Any

from ddk.i18n import t
from ddk.models.fix import FixAttempt

_STEP_MARKS = {"passed": "✓", "failed": "✗", "skipped": "–", "unavailable": "?"}
_MAX_ERROR_CHARS = 160
_MAX_NOTE_CHARS = 110


def describe_stage(stage: str, update: dict[str, Any]) -> str:
    """Progress line for ``stage``, given what the stage returned.

    Each entry of ``_DETAILS`` returns the text after the label, separator included.
    """
    label = _stage_labels().get(stage, stage)
    if update.get("terminal_state") == "manual-review-required":
        message = str(update.get("error_message") or "").strip().splitlines()
        if not message:
            return label
        return label + t(" — 사람 확인 필요: {reason}", reason=message[0][:_MAX_ERROR_CHARS])
    detail = _DETAILS.get(stage, _nothing)(update)
    return f"{label}{detail}"


def _stage_labels() -> dict[str, str]:
    return {
        "intake": t("입력 확인"),
        "repo_scan": t("저장소 분석"),
        "intent_extract": t("디자인 분석"),
        "design_system": t("디자인 시스템 추론"),
        "plan": t("생성 계획"),
        "generate": t("코드 생성"),
        "normalize": t("관례 정리"),
        "validate": t("검증"),
        "autofix": t("자동 수정"),
        "certify": t("판정"),
    }


def _step_labels() -> dict[str, str]:
    return {"build": t("빌드"), "typecheck": t("타입"), "lint": t("린트"), "visual": t("화면")}


def _nothing(update: dict[str, Any]) -> str:
    return ""


def _repo(update: dict[str, Any]) -> str:
    profile = update.get("repo_profile")
    return f" — {profile.framework}" if profile is not None else ""


def _intent(update: dict[str, Any]) -> str:
    graph = update.get("intent_graph")
    if graph is None:
        return ""
    return t(
        " — 영역 {regions}개 · 컴포넌트 {components}개",
        regions=len(graph.layout_regions),
        components=len(graph.components),
    )


def _plan(update: dict[str, Any]) -> str:
    plan = update.get("generation_plan")
    return t(" — 파일 {count}개", count=len(plan.target_files)) if plan is not None else ""


def _generate(update: dict[str, Any]) -> str:
    artifacts = update.get("generated_artifacts")
    return t(" — 파일 {count}개", count=len(artifacts.files)) if artifacts is not None else ""


def _normalize(update: dict[str, Any]) -> str:
    report = update.get("normalization_report")
    if report is None:
        return ""
    text = t(" — {count}개 수정", count=len(report.files_modified))
    if report.skipped_rules:
        text += t(", 건너뜀: {rules}", rules=", ".join(report.skipped_rules))
    return text


def _validate(update: dict[str, Any]) -> str:
    report = update.get("runtime_validation_report")
    if report is None:
        return ""
    parts: list[str] = []
    visual = update.get("visual_regression_report")
    labels = _step_labels()
    for step in report.steps:
        if step.name not in labels:
            continue
        part = f"{labels[step.name]} {_STEP_MARKS[step.status]}"
        if step.name == "visual" and visual is not None:
            part += t(
                " (SSIM {ssim:.2f}, 기준 {threshold:.2f})",
                ssim=visual.ssim_score,
                threshold=visual.threshold,
            )
        parts.append(part)
    return " — " + " · ".join(parts) if parts else ""


def _autofix(update: dict[str, Any]) -> str:
    attempts: list[FixAttempt] = update.get("fix_attempts") or []
    if not attempts:
        return ""
    last = attempts[-1]
    return t(
        " {number}회차 — {note}",
        number=len(attempts),
        note=str(last.patch_description)[:_MAX_NOTE_CHARS],
    )


def _certify(update: dict[str, Any]) -> str:
    decision = update.get("release_decision")
    if decision is None:
        return ""
    scorecard = update.get("scorecard")
    score = t(" (점수 {score:.2f})", score=scorecard.overall) if scorecard is not None else ""
    return f" — {decision.decision}{score}"


_DETAILS = {
    "repo_scan": _repo,
    "intent_extract": _intent,
    "plan": _plan,
    "generate": _generate,
    "normalize": _normalize,
    "validate": _validate,
    "autofix": _autofix,
    "certify": _certify,
}

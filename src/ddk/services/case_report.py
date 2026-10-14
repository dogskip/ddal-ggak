"""The evidence report: one self-contained HTML page that shows why a case got its verdict.

Everything on the page comes from the files in the case folder; nothing is fetched and nothing
is run. Pictures are read from the case folder too, never from the absolute paths recorded in
the reports, so a case that was copied to another machine still renders.
"""

from __future__ import annotations

import base64
import html
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel, TypeAdapter

from ddk import __version__
from ddk.i18n import language, t
from ddk.models.evidence import EvidencePack
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet
from ddk.models.release import ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import RuntimeValidationReport
from ddk.models.visual import VisualRegressionReport

REPORT_NAME = "report.html"
_MAX_IMAGE_WIDTH = 1100
_MAX_PROMPT_CHARS = 600
_ROUND_DIR = re.compile(r"round-(\d+)$")


class ReportUnavailableError(RuntimeError):
    """The case folder has no verdict, so there is nothing to report."""


@dataclass(frozen=True)
class Round:
    """One screenshot comparison: the first run of the page, or the run after a fix."""

    number: int
    visual: VisualRegressionReport
    screenshot: Path | None
    difference: Path | None


@dataclass(frozen=True)
class CaseReport:
    """What the page shows, read from the case folder."""

    case_id: str
    decision: ReleaseDecision
    scorecard: Scorecard | None
    evidence: EvidencePack | None
    validation: RuntimeValidationReport | None
    attempts: list[FixAttempt]
    rounds: list[Round]
    design: Path | None
    generated: GeneratedArtifactSet | None
    calls: list[dict[str, Any]]
    prompt: str


def load_case_report(case_path: Path) -> CaseReport:
    """Read a case folder; only the verdict is required."""
    reports = case_path / "reports"
    decision = _load(reports / "release-decision.json", ReleaseDecision)
    if decision is None:
        raise ReportUnavailableError(
            t("{path} 에 release-decision.json 이 없어 보고서를 만들 수 없습니다", path=reports)
        )
    attempts = _load_list(reports / "fix-attempts.json", FixAttempt)
    case_input = _read_json(reports / "case-input.json")
    return CaseReport(
        case_id=decision.case_id,
        decision=decision,
        scorecard=_load(reports / "scorecard.json", Scorecard),
        evidence=_load(reports / "evidence-pack.json", EvidencePack),
        validation=_load(reports / "runtime-validation-report.json", RuntimeValidationReport),
        attempts=sorted(attempts, key=lambda attempt: attempt.attempt_number),
        rounds=_load_rounds(case_path),
        design=_find_design(case_path, case_input),
        generated=_load(reports / "generated-artifacts.json", GeneratedArtifactSet),
        calls=[
            call for call in _read_json(reports / "llm-calls.json", []) if isinstance(call, dict)
        ],
        prompt=str(case_input.get("prompt", "")) if isinstance(case_input, dict) else "",
    )


def render_html(report: CaseReport) -> str:
    """The page, in the language ``ddk.i18n`` picks."""
    sections = [
        _verdict(report),
        _comparison(report),
        _fixes(report),
        _checks(report),
        _scorecard(report),
        _problems(report),
        _files(report),
        _details(report),
    ]
    title = t("딸깍 증거 보고서 · {case_id}", case_id=report.case_id)
    footer = t(
        "ddk {version} 이(가) 이 case 폴더의 파일만으로 만든 보고서입니다.", version=__version__
    )
    return (
        f'<!doctype html>\n<html lang="{language()}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f"<title>{_e(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n<main>\n"
        f'<header><p class="brand">ddalggak</p><h1>{_e(title)}</h1></header>\n'
        + "\n".join(section for section in sections if section)
        + f"\n<footer>{_e(footer)}</footer>\n"
        f"</main>\n<script>{_SCRIPT}</script>\n</body>\n</html>\n"
    )


def write_report(case_path: Path, output: Path | None = None) -> Path:
    """Write the page next to the case's other reports, or to ``output``."""
    page = render_html(load_case_report(case_path))
    target = output or case_path / "reports" / REPORT_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# Reading the case folder
# ---------------------------------------------------------------------------


def _read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _load[M: BaseModel](path: Path, model: type[M]) -> M | None:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _load_list[M: BaseModel](path: Path, model: type[M]) -> list[M]:
    try:
        return TypeAdapter(list[model]).validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _load_rounds(case_path: Path) -> list[Round]:
    visual_dir = case_path / "artifacts" / "visual"
    rounds: list[Round] = []
    for folder in visual_dir.glob("round-*"):
        match = _ROUND_DIR.match(folder.name)
        saved = _load(folder / "report.json", VisualRegressionReport)
        if match and saved is not None:
            rounds.append(
                Round(
                    number=int(match.group(1)),
                    visual=saved,
                    screenshot=_existing(folder / "generated.png"),
                    difference=_existing(folder / "diff.png"),
                )
            )
    if rounds:
        return sorted(rounds, key=lambda round_: round_.number)
    # A case from before rounds were kept has only the latest comparison.
    legacy = _load(case_path / "reports" / "visual-regression-report.json", VisualRegressionReport)
    if legacy is None:
        return []
    return [
        Round(
            number=1,
            visual=legacy,
            screenshot=_existing(visual_dir / "generated.png"),
            difference=_existing(visual_dir / "diff.png"),
        )
    ]


def _find_design(case_path: Path, case_input: Any) -> Path | None:
    inputs = case_path / "artifacts" / "inputs"
    if isinstance(case_input, dict):
        names = case_input.get("image_paths")
        if isinstance(names, list) and names:
            named = _existing(inputs / Path(str(names[0])).name)
            if named is not None:
                return named
    candidates = sorted(inputs.glob("*")) if inputs.is_dir() else []
    return next((p for p in candidates if p.is_file()), None)


def _existing(path: Path) -> Path | None:
    return path if path.is_file() else None


# ---------------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------------


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _data_uri(path: Path | None) -> str | None:
    """The picture as a ``data:`` URI, shrunk to a readable width; ``None`` when unreadable."""
    if path is None:
        return None
    try:
        with Image.open(path) as source:
            image = source.convert("RGBA" if "A" in source.getbands() else "RGB")
        if image.width > _MAX_IMAGE_WIDTH:
            height = max(1, round(image.height * _MAX_IMAGE_WIDTH / image.width))
            image = image.resize((_MAX_IMAGE_WIDTH, height), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
    except (OSError, ValueError):
        return None
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _figure(path: Path | None, caption: str) -> str:
    uri = _data_uri(path)
    inner = (
        f'<img src="{uri}" alt="{_e(caption)}">'
        if uri is not None
        else f'<p class="missing">{_e(t("이미지를 불러올 수 없습니다"))}</p>'
    )
    return f"<figure>{inner}<figcaption>{_e(caption)}</figcaption></figure>"


def _aspect(path: Path | None) -> str:
    try:
        assert path is not None
        with Image.open(path) as image:
            return f"{image.width} / {image.height}"
    except (AssertionError, OSError):
        return "16 / 10"


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------


def _card(title: str, body: str, *, tone: str = "") -> str:
    return f'<section class="card {tone}"><h2>{_e(title)}</h2>\n{body}\n</section>'


def _verdict(report: CaseReport) -> str:
    tone, label = _verdict_label(report.decision.decision)
    score = report.scorecard
    big = (
        f'<p class="score"><span>{score.overall:.2f}</span> '
        f"<small>{_e(t('점수'))} · {_e(t('등급'))} {_e(score.grade)}</small></p>"
        if score is not None
        else ""
    )
    facts: list[str] = []
    if report.evidence is not None:
        seconds = report.evidence.pipeline_duration_ms / 1000
        facts.append(_e(t("소요 {seconds:.1f}초", seconds=seconds)))
        facts.append(_e(t("비용 ${cost:.4f}", cost=report.evidence.total_cost_usd)))
    if report.calls:
        facts.append(_e(t("모델 호출 {count}회", count=len(report.calls))))
    if report.attempts:
        facts.append(_e(t("자동 수정 {count}회", count=len(report.attempts))))
    return (
        f'<section class="card verdict {tone}" data-decision="{_e(report.decision.decision)}">'
        f'<div><p class="pill {tone}">{_e(label)}</p>'
        f"<p>{_e(report.decision.summary)}</p>"
        f'<p class="facts">{" · ".join(facts)}</p></div>{big}</section>'
    )


def _verdict_label(decision: str) -> tuple[str, str]:
    if decision == "ready":
        return "ok", t("적용 가능")
    if decision == "blocked":
        return "bad", t("차단됨")
    return "warn", t("사람 검토 필요")


def _comparison(report: CaseReport) -> str:
    if not report.rounds:
        return ""
    parts: list[str] = []
    for index, round_ in enumerate(report.rounds):
        visual = round_.visual
        tone, state = ("ok", t("통과")) if visual.pass_result else ("bad", t("미달"))
        numbers = t(
            "SSIM {ssim:.2f} (기준 {threshold:.2f}) · 디자인과 크게 다른 면적 {share:.1%} "
            "(허용 {allowed:.1%})",
            ssim=visual.ssim_score,
            threshold=visual.threshold,
            share=visual.mismatch_area_ratio,
            allowed=visual.max_mismatch_ratio,
        )
        figures = [
            _figure(round_.screenshot, t("결과 화면")),
            _figure(round_.difference, t("차이 (빨강)")),
        ]
        if index == 0:
            figures.insert(0, _figure(report.design, t("디자인")))
        parts.append(
            f'<div class="round"><h3>{_e(t("{number}회차 검증", number=round_.number))} '
            f'<span class="pill {tone}">{_e(state)}</span></h3>'
            f'<p class="nums">{_e(numbers)}</p><div class="figures">{"".join(figures)}</div></div>'
        )
    parts.append(_overlay(report))
    return _card(t("화면 비교"), "\n".join(part for part in parts if part))


def _overlay(report: CaseReport) -> str:
    final = report.rounds[-1].screenshot if report.rounds else None
    design_uri, result_uri = _data_uri(report.design), _data_uri(final)
    if design_uri is None or result_uri is None:
        return ""
    hint = t("왼쪽은 결과 화면, 오른쪽은 디자인입니다. 막대를 끌어 비교하세요.")
    return (
        f'<div class="round"><h3>{_e(t("디자인과 겹쳐 보기"))}</h3>'
        f'<div class="compare" data-compare style="aspect-ratio: {_aspect(report.design)}">'
        f'<img class="base" src="{design_uri}" alt="{_e(t("디자인"))}">'
        f'<img class="over" src="{result_uri}" alt="{_e(t("결과 화면"))}">'
        f'<input type="range" min="0" max="100" value="50" aria-label="{_e(t("겹침 위치"))}">'
        f'</div><p class="hint">{_e(hint)}</p></div>'
    )


def _table(head: str, rows: str) -> str:
    """A table that scrolls inside its card on a narrow screen instead of the whole page."""
    return (
        f'<div class="scroll"><table><thead><tr>{head}</tr></thead>'
        f"<tbody>{rows}</tbody></table></div>"
    )


def _fixes(report: CaseReport) -> str:
    if not report.attempts:
        return ""
    rows = "".join(
        f"<tr><td>{attempt.attempt_number}</td><td><code>{_e(attempt.rule_id)}</code></td>"
        f"<td>{_e(attempt.patch_description)}</td>"
        f"<td>{_e(', '.join(attempt.files_patched))}</td>"
        f"<td>{'✓' if attempt.success else '✗'}</td></tr>"
        for attempt in report.attempts
    )
    head = "".join(
        f"<th>{_e(label)}</th>"
        for label in (t("회차"), t("규칙"), t("조치"), t("고친 파일"), t("결과"))
    )
    return _card(t("자동 수정"), _table(head, rows))


def _checks(report: CaseReport) -> str:
    if report.validation is None or not report.validation.steps:
        return ""
    marks = {
        "passed": ("ok", "✓", t("통과")),
        "failed": ("bad", "✗", t("실패")),
        "skipped": ("", "–", t("건너뜀")),
        "unavailable": ("warn", "?", t("실행 불가")),
    }
    rows = ""
    for step in report.validation.steps:
        tone, mark, word = marks[step.status]
        rows += (
            f"<tr><td><code>{_e(step.name)}</code></td>"
            f'<td class="{tone}">{mark} {_e(word)}</td>'
            f"<td>{step.duration_ms / 1000:.1f}s</td><td>{_e(step.summary)}</td></tr>"
        )
    head = "".join(
        f"<th>{_e(label)}</th>" for label in (t("단계"), t("상태"), t("시간"), t("내용"))
    )
    return _card(t("검사 단계"), _table(head, rows))


def _scorecard(report: CaseReport) -> str:
    score = report.scorecard
    if score is None:
        return ""
    bars = ""
    for label, value in (
        (t("정밀도"), score.precision),
        (t("유지보수성"), score.maintainability),
        (t("자동화"), score.automation),
        (t("확장성"), score.scalability),
    ):
        bars += (
            f'<div class="bar"><span>{_e(label)}</span>'
            f'<div class="track"><div style="width:{value * 100:.0f}%"></div></div>'
            f"<b>{value:.2f}</b></div>"
        )
    return _card(t("점수표"), bars)


def _problems(report: CaseReport) -> str:
    parts: list[str] = []
    if report.decision.blockers:
        items = "".join(
            f'<li><code>{_e(b.id)}</code> <span class="tag">{_e(b.severity)}</span> '
            f"{_e(b.description)}</li>"
            for b in report.decision.blockers
        )
        parts.append(f"<h3>{_e(t('차단 항목'))}</h3><ul>{items}</ul>")
    failures = report.validation.failures if report.validation is not None else []
    if failures:
        items = "".join(
            f"<li><code>{_e(f.taxonomy_id)}</code> {_e(f.message)}"
            + (f" <small>({_e(f.file_path)})</small>" if f.file_path else "")
            + "</li>"
            for f in failures
        )
        parts.append(f"<h3>{_e(t('실패 기록'))}</h3><ul>{items}</ul>")
    if not parts:
        return ""
    return _card(t("문제"), "\n".join(parts), tone="problems")


def _files(report: CaseReport) -> str:
    if report.generated is None or not report.generated.files:
        return ""
    items = "".join(
        f"<li><code>{_e(file.path)}</code> "
        f"<small>{_e(t('{count}줄', count=_line_count(file.content)))}</small></li>"
        for file in report.generated.files
    )
    return _card(t("생성된 파일"), f"<ul>{items}</ul>")


def _line_count(text: str) -> int:
    return text.count("\n") + (0 if text.endswith("\n") or not text else 1)


def _details(report: CaseReport) -> str:
    rows: list[tuple[str, str]] = [("case", report.case_id)]
    if report.prompt:
        rows.append((t("지시"), report.prompt[:_MAX_PROMPT_CHARS]))
    rows.append((t("판정 시각"), report.decision.created_at.strftime("%Y-%m-%d %H:%M UTC")))
    models = sorted({str(call["model"]) for call in report.calls if call.get("model")})
    if models:
        rows.append((t("모델"), ", ".join(models)))
    if report.calls:
        tokens_in = sum(int(call.get("input_tokens") or 0) for call in report.calls)
        tokens_out = sum(int(call.get("output_tokens") or 0) for call in report.calls)
        rows.append((t("토큰 (입력 / 출력)"), f"{tokens_in:,} / {tokens_out:,}"))
    if report.rounds:
        visual = report.rounds[-1].visual
        if visual.viewport:
            rows.append((t("화면 크기"), visual.viewport))
    body = "".join(f"<dt>{_e(key)}</dt><dd>{_e(value)}</dd>" for key, value in rows)
    return _card(t("실행 정보"), f"<dl>{body}</dl>")


_SCRIPT = """
document.querySelectorAll('[data-compare]').forEach(function (box) {
  var over = box.querySelector('.over'), range = box.querySelector('input');
  function show() { over.style.clipPath = 'inset(0 ' + (100 - range.value) + '% 0 0)'; }
  range.addEventListener('input', show);
  show();
});
""".strip()

_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--ink:#14171c;--muted:#5b6472;--line:#e3e7ee;--ok:#117a43;
--ok-bg:#e1f5ea;--bad:#b42318;--bad-bg:#fde8e6;--warn:#8a5a00;--warn-bg:#fff0cf;--accent:#3358d4;
--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#0f1217;--card:#171b22;--ink:#e8ebf0;--muted:#98a2b3;
--line:#262c36;--ok:#4ade80;--ok-bg:#12301f;--bad:#f87171;--bad-bg:#3a1714;--warn:#fbbf24;
--warn-bg:#3a2d0b;--accent:#8aa4ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,-apple-system,
"Segoe UI",Roboto,"Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}
header{margin-bottom:16px}.brand{margin:0;color:var(--muted);font-weight:600;letter-spacing:.04em}
h1{margin:.1em 0 0;font-size:1.6rem}h2{margin:0 0 12px;font-size:1.1rem}
h3{margin:16px 0 8px;font-size:1rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px 20px;margin:14px 0}
.verdict{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap}
.verdict.ok{border-left:6px solid var(--ok)}.verdict.bad{border-left:6px solid var(--bad)}
.verdict.warn{border-left:6px solid var(--warn)}
.score{margin:0;text-align:right}.score span{font-size:2.6rem;font-weight:700;line-height:1}
.score small,.facts,.hint,small{color:var(--muted)}.facts,.hint{margin:.3em 0 0}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:600;font-size:.9rem}
.pill.ok{background:var(--ok-bg);color:var(--ok)}.pill.bad{background:var(--bad-bg);color:var(--bad)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
td.ok{color:var(--ok)}td.bad{color:var(--bad)}td.warn{color:var(--warn)}
code{font-family:var(--mono);font-size:.88em}
.tag{font-size:.75rem;border:1px solid var(--line);border-radius:4px;padding:0 5px;
color:var(--muted)}
.nums{margin:.2em 0 10px;color:var(--muted)}
.figures{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
figure{margin:0}figure img{width:100%;height:auto;display:block;border:1px solid var(--line);
border-radius:8px;background:#fff}
figcaption{margin-top:4px;color:var(--muted);font-size:.85rem}.missing{color:var(--muted)}
.compare{position:relative;width:100%;max-width:960px;border:1px solid var(--line);
border-radius:8px;
overflow:hidden;background:#fff}
.compare img{position:absolute;inset:0;width:100%;height:100%}
.over{clip-path:inset(0 50% 0 0)}
.compare input{position:absolute;left:0;right:0;bottom:6px;width:100%;margin:0}
.round+.round{border-top:1px solid var(--line);margin-top:14px;padding-top:2px}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:6px 8px;
border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.bar{display:grid;grid-template-columns:120px 1fr 48px;gap:10px;align-items:center;margin:6px 0}
.track{height:10px;background:var(--line);border-radius:5px;overflow:hidden}
.track div{height:100%;background:var(--accent)}
ul{margin:0;padding-left:20px}
dl{display:grid;grid-template-columns:max-content 1fr;gap:4px 16px;margin:0}
dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
footer{margin-top:24px;color:var(--muted);font-size:.85rem;text-align:center}
@media (max-width:560px){.bar{grid-template-columns:90px 1fr 40px}.score{text-align:left}}
""".strip()

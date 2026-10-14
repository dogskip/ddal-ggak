"""A case folder on disk, written the way ``CaseArtifactStore`` writes it."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ddk.models.evidence import EvidencePack
from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.release import BlockerItem, ReleaseDecision
from ddk.models.scorecard import Scorecard
from ddk.models.validation import FailureRecord, RuntimeValidationReport, ValidationStep
from ddk.models.visual import VisualRegressionReport


def _png(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (320, 200)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)


def make_case(
    repo: Path,
    *,
    case_id: str = "C-001",
    decision: str = "ready",
    ssims: tuple[float, ...] = (0.88, 0.99),
    attempt_note: str = "R-10: model adjusted src/App.tsx toward the design",
    failure_message: str = "SSIM 0.88 is below 0.92",
    file_path: str = "src/App.tsx",
    design_size: tuple[int, int] = (320, 200),
    with_images: bool = True,
) -> Path:
    """Write a finished case whose visual rounds have the given scores; return its folder."""
    case = repo / ".ddk" / "cases" / case_id
    reports = case / "reports"
    visual = case / "artifacts" / "visual"
    reports.mkdir(parents=True)

    def put(name: str, model: object) -> None:
        (reports / name).write_text(model.model_dump_json(indent=2), encoding="utf-8")  # type: ignore[attr-defined]

    ready = decision == "ready"
    put(
        "release-decision.json",
        ReleaseDecision(
            case_id=case_id,
            decision=decision,  # type: ignore[arg-type]
            summary=f"Release {decision} with overall score 0.96 (A).",
            blockers=[]
            if ready
            else [
                BlockerItem(
                    id="visual-mismatch",
                    category="visual",
                    description=failure_message,
                    severity="blocker",
                )
            ],
        ),
    )
    put(
        "scorecard.json",
        Scorecard(
            case_id=case_id,
            precision=1.0,
            maintainability=0.95,
            automation=0.9,
            scalability=0.8,
            overall=0.96,
            grade="A",
        ),
    )
    put(
        "evidence-pack.json",
        EvidencePack(
            case_id=case_id,
            total_cost_usd=0.0123,
            pipeline_duration_ms=6603,
            terminal_state=decision,
        ),
    )
    attempts = [
        FixAttempt(
            attempt_number=n,
            case_id=case_id,
            trigger_failures=["f"],
            rule_id="R-10",
            files_patched=[file_path],
            patch_description=attempt_note,
            success=True,
        )
        for n in range(1, len(ssims))
    ]
    (reports / "fix-attempts.json").write_text(
        json.dumps([a.model_dump(mode="json") for a in attempts]), encoding="utf-8"
    )
    put(
        "runtime-validation-report.json",
        RuntimeValidationReport(
            case_id=case_id,
            build_success=True,
            type_check_success=True,
            lint_success=True,
            steps=[
                ValidationStep(name="build", status="passed", duration_ms=1350),
                ValidationStep(name="typecheck", status="passed", duration_ms=445),
                ValidationStep(
                    name="visual",
                    status="passed" if ready else "failed",
                    duration_ms=2960,
                    summary="SSIM 0.99 (min 0.92)",
                ),
            ],
            failures=[]
            if ready
            else [
                FailureRecord(
                    id="f1",
                    taxonomy_id="FT-VISUAL-001",
                    severity="major",
                    message=failure_message,
                    file_path=file_path,
                    source="visual",
                )
            ],
        ),
    )
    put(
        "generated-artifacts.json",
        GeneratedArtifactSet(
            case_id=case_id,
            files=[
                GeneratedFile(
                    path=file_path,
                    content="export const App = () => <main />;\nexport default App;\n",
                    source_node_id="n1",
                )
            ],
        ),
    )
    (reports / "llm-calls.json").write_text(
        json.dumps(
            [
                {
                    "sequence": 1,
                    "purpose": "generate",
                    "model": "claude-sonnet-5-5",
                    "status": "ok",
                    "input_tokens": 1200,
                    "output_tokens": 800,
                    "cost_usd": 0.01,
                },
                {
                    "sequence": 2,
                    "purpose": "autofix",
                    "model": "claude-haiku-5-5",
                    "status": "ok",
                    "input_tokens": 300,
                    "output_tokens": 100,
                    "cost_usd": 0.0023,
                },
            ]
        ),
        encoding="utf-8",
    )
    (reports / "case-input.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "image_paths": [str(repo / "design.png")],
                "prompt": "Build the dashboard shown in the design",
                "repo_path": str(repo),
            }
        ),
        encoding="utf-8",
    )

    for number, ssim in enumerate(ssims, start=1):
        passed = ssim >= 0.92
        round_dir = visual / f"round-{number}"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "report.json").write_text(
            VisualRegressionReport(
                case_id=case_id,
                # Absolute paths from the machine that ran the case; the report must not use them.
                reference_path="/gone/design.png",
                generated_path="/gone/generated.png",
                ssim_score=ssim,
                pass_result=passed,
                mismatch_area_ratio=0.0 if passed else 0.063,
                viewport=f"{design_size[0]}x{design_size[1]}",
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )
        if with_images:
            _png(round_dir / "generated.png", (250 - number * 10, 250, 250), design_size)
            _png(round_dir / "diff.png", (255, 0, 0), design_size)
    if with_images:
        _png(case / "artifacts" / "inputs" / "design.png", (255, 255, 255), design_size)
    return case

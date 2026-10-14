"""describe_stage turns what a graph stage returned into one readable line."""

from __future__ import annotations

from ddk.models.fix import FixAttempt
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile, GenerationPlan
from ddk.models.normalization import NormalizationReport
from ddk.models.release import ReleaseDecision
from ddk.models.repo import RepoProfile
from ddk.models.scorecard import Scorecard
from ddk.models.validation import RuntimeValidationReport, ValidationStep
from ddk.models.visual import VisualRegressionReport
from ddk.services.progress import describe_stage


def _steps(**statuses: str) -> list[ValidationStep]:
    return [ValidationStep(name=name, status=status) for name, status in statuses.items()]  # type: ignore[arg-type]


def _report(steps: list[ValidationStep]) -> RuntimeValidationReport:
    return RuntimeValidationReport(
        case_id="C-001",
        build_success=True,
        type_check_success=True,
        lint_success=True,
        steps=steps,
    )


def _visual(score: float, passed: bool) -> VisualRegressionReport:
    return VisualRegressionReport(
        case_id="C-001",
        reference_path="r.png",
        generated_path="g.png",
        ssim_score=score,
        pass_result=passed,
    )


def test_repository_analysis_names_the_framework() -> None:
    line = describe_stage("repo_scan", {"repo_profile": RepoProfile(framework="react")})

    assert line == "저장소 분석 — react"


def test_plan_and_generate_count_files() -> None:
    plan = GenerationPlan(case_id="C-001", nodes=[], target_files=["a.tsx", "b.tsx"])
    artifacts = GeneratedArtifactSet(
        case_id="C-001",
        files=[GeneratedFile(path="a.tsx", content="x", source_node_id="n")],
    )

    assert describe_stage("plan", {"generation_plan": plan}) == "생성 계획 — 파일 2개"
    assert describe_stage("generate", {"generated_artifacts": artifacts}) == "코드 생성 — 파일 1개"


def test_normalization_reports_patched_and_skipped() -> None:
    report = NormalizationReport(
        case_id="C-001", files_modified=["a.tsx"], skipped_rules=["normalization-truncated"]
    )

    line = describe_stage("normalize", {"normalization_report": report})

    assert line == "관례 정리 — 1개 수정, 건너뜀: normalization-truncated"


def test_validation_shows_every_step_and_the_visual_score() -> None:
    update = {
        "runtime_validation_report": _report(
            _steps(build="passed", typecheck="passed", lint="passed", visual="failed")
        ),
        "visual_regression_report": _visual(0.78, False),
    }

    line = describe_stage("validate", update)

    assert line == "검증 — 빌드 ✓ · 타입 ✓ · 린트 ✓ · 화면 ✗ (SSIM 0.78, 기준 0.92)"


def test_validation_marks_skipped_and_unavailable_steps() -> None:
    update = {
        "runtime_validation_report": _report(
            _steps(build="passed", typecheck="skipped", visual="unavailable")
        )
    }

    assert describe_stage("validate", update) == "검증 — 빌드 ✓ · 타입 – · 화면 ?"


def test_autofix_names_the_attempt() -> None:
    attempt = FixAttempt(
        attempt_number=2,
        case_id="C-001",
        rule_id="R-10",
        patch_description="R-10: model adjusted src/App.tsx toward the design",
        success=True,
    )

    line = describe_stage("autofix", {"fix_attempts": [attempt, attempt]})

    assert line == "자동 수정 2회차 — R-10: model adjusted src/App.tsx toward the design"


def test_certification_shows_decision_and_score() -> None:
    scorecard = Scorecard(
        case_id="C-001",
        precision=1,
        maintainability=1,
        automation=1,
        scalability=1,
        overall=0.934,
        grade="A",
    )
    update = {
        "release_decision": ReleaseDecision(case_id="C-001", decision="ready"),
        "scorecard": scorecard,
    }

    assert describe_stage("certify", update) == "판정 — ready (점수 0.93)"


def test_stage_that_needs_a_human_shows_why() -> None:
    update = {
        "terminal_state": "manual-review-required",
        "error_message": "Node n1: the model returned no usable file.\nsecond line",
    }

    line = describe_stage("generate", update)

    assert line == "코드 생성 — 사람 확인 필요: Node n1: the model returned no usable file."


def test_unknown_stage_and_missing_data_do_not_break() -> None:
    assert describe_stage("intake", {}) == "입력 확인"
    assert describe_stage("validate", {}) == "검증"
    assert describe_stage("something-new", {}) == "something-new"

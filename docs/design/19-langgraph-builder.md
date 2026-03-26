# LangGraph StateGraph Builder 명세

> `graph/builder.py`의 실제 구현 계약.
> 이 문서 없이는 LangGraph 그래프 연결 코드를 작성할 수 없다.

---

## 1. StateGraph 빌드 코드

```python
# src/ddk/graph/builder.py

from langgraph.graph import StateGraph, END
from .state import GraphState
from .edges import (
    route_after_analyze,
    route_after_validate,
    route_after_visual,
    route_after_fix,
    route_after_certify,
)
from .nodes import (
    ingest_node,
    repo_scan_node,
    intent_extract_node,
    plan_node,
    generate_node,
    normalize_node,
    runtime_validate_node,
    visual_regress_node,
    auto_fix_node,
    certify_node,
)


def build_ddk_graph() -> "CompiledGraph":
    """
    딸깍 메인 파이프라인 그래프.

    흐름:
    ingest → repo_scan → intent_extract → plan → generate
         → normalize → runtime_validate → [pass: visual_regress | fail: auto_fix]
         → [pass: certify | fail: auto_fix]
         → [certified-ready | certified-blocked | manual-review-required] → END
    """
    workflow = StateGraph(GraphState)

    # 노드 등록
    workflow.add_node("ingest", ingest_node)
    workflow.add_node("repo_scan", repo_scan_node)
    workflow.add_node("intent_extract", intent_extract_node)
    workflow.add_node("plan", plan_node)
    workflow.add_node("generate", generate_node)
    workflow.add_node("normalize", normalize_node)
    workflow.add_node("runtime_validate", runtime_validate_node)
    workflow.add_node("visual_regress", visual_regress_node)
    workflow.add_node("auto_fix", auto_fix_node)
    workflow.add_node("certify", certify_node)

    # 시작점
    workflow.set_entry_point("ingest")

    # 직선 엣지 (조건 없음)
    workflow.add_edge("ingest", "repo_scan")
    workflow.add_edge("repo_scan", "intent_extract")
    workflow.add_edge("intent_extract", "plan")
    workflow.add_edge("plan", "generate")
    workflow.add_edge("generate", "normalize")
    workflow.add_edge("normalize", "runtime_validate")

    # 조건부 엣지: runtime_validate 이후
    workflow.add_conditional_edges(
        "runtime_validate",
        route_after_validate,
        {
            "visual_regress": "visual_regress",  # runtime pass → visual 검사
            "auto_fix": "auto_fix",               # runtime fail → 자동 수정
            "certify": "certify",                  # skip_visual=True 시
        },
    )

    # 조건부 엣지: visual_regress 이후
    workflow.add_conditional_edges(
        "visual_regress",
        route_after_visual,
        {
            "certify": "certify",       # visual pass → 인증
            "auto_fix": "auto_fix",     # visual fail → 자동 수정
        },
    )

    # 조건부 엣지: auto_fix 이후
    workflow.add_conditional_edges(
        "auto_fix",
        route_after_fix,
        {
            "runtime_validate": "runtime_validate",  # fix 시도 후 재검증
            "certify": "certify",                     # pass 시 인증
            END: END,                                 # budget 소진 or regression → 종료
        },
    )

    # 조건부 엣지: certify 이후
    workflow.add_conditional_edges(
        "certify",
        route_after_certify,
        {
            END: END,  # 항상 종료 (certified-ready or blocked)
        },
    )

    return workflow.compile()
```

---

## 2. 각 노드 함수 시그니처

모든 노드는 `GraphState`를 받아 변경된 필드만 dict로 반환한다.
LangGraph는 반환된 dict를 state에 merge한다.

```python
# src/ddk/graph/nodes/ingest.py
from ddk.graph.state import GraphState
from ddk.workspace.manager import WorkspaceManager
from ddk.models.input import CaseInput

async def ingest_node(state: GraphState) -> dict:
    """
    CaseInput artifact를 workspace에 저장.
    state.case_input이 이미 있으면 그대로.
    """
    # state.case_input은 CLI에서 주입 (그래프 진입 전)
    ws = WorkspaceManager.from_state(state)
    ws.save_artifact("input.json", state["case_input"])
    return {"current_node": "ingest"}
```

```python
# src/ddk/graph/nodes/repo_scan.py
from ddk.graph.state import GraphState
from ddk.services.repo_scanner import RepoConventionScanner

async def repo_scan_node(state: GraphState) -> dict:
    """
    Input:  state["case_input"].repo_path
    Output: state["repo_profile"]
    """
    scanner = RepoConventionScanner()
    profile = await scanner.scan(state["case_input"].repo_path)
    return {"repo_profile": profile, "current_node": "repo_scan"}
```

```python
# src/ddk/graph/nodes/intent_extract.py
from ddk.graph.state import GraphState
from ddk.services.intent_extractor import SemanticIntentExtractor

async def intent_extract_node(state: GraphState) -> dict:
    """
    Input:  state["case_input"].image_paths, state["case_input"].prompt
    Output: state["intent_graph"], state["llm_call_records"] (appended)
    """
    extractor = SemanticIntentExtractor.from_config()
    graph, record = await extractor.extract(
        image_paths=state["case_input"].image_paths,
        prompt=state["case_input"].prompt,
        reference_notes=state["case_input"].reference_notes,
    )
    return {
        "intent_graph": graph,
        "llm_call_records": state["llm_call_records"] + [record.call_id],
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0),
        "current_node": "intent_extract",
    }
```

```python
# src/ddk/graph/nodes/plan.py
from ddk.graph.state import GraphState
from ddk.services.generation_planner import GenerationPlanner

async def plan_node(state: GraphState) -> dict:
    """
    Input:  state["intent_graph"], state["repo_profile"]
    Output: state["generation_plan"]
    """
    planner = GenerationPlanner.from_config()
    plan, record = await planner.plan(
        intent_graph=state["intent_graph"],
        repo_profile=state["repo_profile"],
        prompt=state["case_input"].prompt,
    )
    return {
        "generation_plan": plan,
        "llm_call_records": state["llm_call_records"] + [record.call_id],
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0),
        "current_node": "plan",
    }
```

```python
# src/ddk/graph/nodes/generate.py
from ddk.graph.state import GraphState
from ddk.services.code_generator import CodeGenerator

async def generate_node(state: GraphState) -> dict:
    """
    Input:  state["generation_plan"], state["repo_profile"], state["intent_graph"]
    Output: state["generated_artifacts"]
    각 GenerationNode를 순서대로 처리 (execution_order 기준)
    """
    generator = CodeGenerator.from_config()
    artifacts, records = await generator.generate_all(
        plan=state["generation_plan"],
        repo_profile=state["repo_profile"],
        intent_graph=state["intent_graph"],
        prompt=state["case_input"].prompt,
    )
    new_records = [r.call_id for r in records]
    new_cost = sum(r.cost_usd or 0.0 for r in records)
    return {
        "generated_artifacts": artifacts,
        "llm_call_records": state["llm_call_records"] + new_records,
        "total_cost_usd": state["total_cost_usd"] + new_cost,
        "current_node": "generate",
    }
```

```python
# src/ddk/graph/nodes/normalize.py
from ddk.graph.state import GraphState
from ddk.services.normalizer import OutputNormalizer

async def normalize_node(state: GraphState) -> dict:
    """
    Input:  state["generated_artifacts"], state["repo_profile"]
    Output: state["normalization_report"], state["generated_artifacts"] (수정됨)
    """
    normalizer = OutputNormalizer.from_config()
    report, patched_artifacts = await normalizer.normalize(
        artifacts=state["generated_artifacts"],
        repo_profile=state["repo_profile"],
    )
    return {
        "normalization_report": report,
        "generated_artifacts": patched_artifacts,
        "current_node": "normalize",
    }
```

```python
# src/ddk/graph/nodes/runtime_validate.py
from ddk.graph.state import GraphState
from ddk.services.runtime_validator import RuntimeValidationAggregator

async def runtime_validate_node(state: GraphState) -> dict:
    """
    Input:  state["generated_artifacts"], state["case_input"].repo_path
    Output: state["runtime_validation_report"]
    sandbox 안에서 실행됨.
    """
    validator = RuntimeValidationAggregator.from_config()
    report = await validator.validate(
        artifacts=state["generated_artifacts"],
        repo_path=state["case_input"].repo_path,
        case_id=state["case_id"],
        pre_run_ref=state.get("pre_run_checkpoint_ref"),
    )
    return {
        "runtime_validation_report": report,
        "current_node": "runtime_validate",
    }
```

```python
# src/ddk/graph/nodes/visual_regress.py
from ddk.graph.state import GraphState
from ddk.services.visual_regression import VisualRegressionService

async def visual_regress_node(state: GraphState) -> dict:
    """
    Input:  state["case_input"].visual_reference_paths
    Output: state["visual_regression_report"]
    Playwright로 스크린샷 캡처 후 SSIM 비교.
    """
    svc = VisualRegressionService.from_config()
    report = await svc.compare(
        reference_paths=state["case_input"].visual_reference_paths,
        repo_path=state["case_input"].repo_path,
        case_id=state["case_id"],
    )
    return {
        "visual_regression_report": report,
        "current_node": "visual_regress",
    }
```

```python
# src/ddk/graph/nodes/auto_fix.py
from ddk.graph.state import GraphState
from ddk.services.auto_fix_planner import AutoFixPlanner
from ddk.services.retry_controller import RetryBudgetController

async def auto_fix_node(state: GraphState) -> dict:
    """
    Input:  state["runtime_validation_report"] 또는 state["visual_regression_report"]
    Output: state["fix_attempts"] (appended), state["generated_artifacts"] (수정됨)
    RetryBudgetController가 소진/비개선 감지 시 terminal_state 설정.
    """
    controller = RetryBudgetController(
        max_retries=3,
        budget_remaining=state["retry_budget_remaining"],
    )
    planner = AutoFixPlanner.from_config()

    failures = _collect_failures(state)
    is_non_improving = controller.is_non_improving(
        state["fix_attempts"], failures
    )

    if is_non_improving or state["retry_budget_remaining"] <= 0:
        return {
            "terminal_state": "manual-review-required",
            "current_node": "auto_fix",
        }

    attempt, patched, record = await planner.fix(
        failures=failures,
        artifacts=state["generated_artifacts"],
        previous_attempts=state["fix_attempts"],
        repo_profile=state["repo_profile"],
        attempt_no=len(state["fix_attempts"]) + 1,
    )

    return {
        "generated_artifacts": patched,
        "fix_attempts": state["fix_attempts"] + [attempt],
        "retry_budget_remaining": state["retry_budget_remaining"] - 1,
        "llm_call_records": state["llm_call_records"] + ([record.call_id] if record else []),
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0 if record else 0.0),
        "current_node": "auto_fix",
    }

def _collect_failures(state: GraphState) -> list:
    failures = []
    if state.get("runtime_validation_report"):
        failures.extend(state["runtime_validation_report"].all_failures)
    if state.get("visual_regression_report") and \
       state["visual_regression_report"].overall_status == "fail":
        from ddk.models.validation import FailureRecord
        failures.append(FailureRecord(
            taxonomy_id="VISUAL-001",
            severity="critical",
            message=f"SSIM={state['visual_regression_report'].ssim:.2f}",
        ))
    return failures
```

```python
# src/ddk/graph/nodes/certify.py
from ddk.graph.state import GraphState
from ddk.services.benchmark_service import BenchmarkScorecardService
from ddk.services.release_decision import ReleaseDecisionService
from ddk.services.evidence_builder import EvidencePackBuilder

async def certify_node(state: GraphState) -> dict:
    """
    Input:  모든 report artifacts
    Output: state["scorecard"], state["release_decision"], state["evidence_pack"]
    """
    scorer = BenchmarkScorecardService.from_config()
    scorecard = scorer.compute(state)

    decider = ReleaseDecisionService()
    decision = decider.decide(state, scorecard)

    builder = EvidencePackBuilder()
    pack = builder.build(state, scorecard, decision)

    return {
        "scorecard": scorecard,
        "release_decision": decision,
        "evidence_pack": pack,
        "terminal_state": decision.status,
        "current_node": "certify",
    }
```

---

## 3. Edge 조건 함수

```python
# src/ddk/graph/edges.py

from langgraph.graph import END
from .state import GraphState


def route_after_validate(state: GraphState) -> str:
    """
    runtime_validate 이후 분기.
    - overall_status == "pass" → visual_regress (또는 certify if skip_visual)
    - overall_status == "fail" → auto_fix (budget 있을 때)
    - budget 없음 → certify (blocked 상태로)
    """
    report = state.get("runtime_validation_report")
    if not report:
        return "certify"  # validation 스킵된 경우 → certify로 직행

    if report.overall_status == "pass":
        # visual reference가 없으면 바로 certify
        if not state["case_input"].visual_reference_paths:
            return "certify"
        return "visual_regress"

    # fail
    if state["retry_budget_remaining"] > 0:
        return "auto_fix"
    return "certify"  # budget 소진 → certify (blocked)


def route_after_visual(state: GraphState) -> str:
    """
    visual_regress 이후 분기.
    - pass → certify
    - fail + budget > 0 → auto_fix
    - fail + budget == 0 → certify (blocked)
    """
    report = state.get("visual_regression_report")
    if not report or report.overall_status == "pass":
        return "certify"

    if state["retry_budget_remaining"] > 0:
        return "auto_fix"
    return "certify"


def route_after_fix(state: GraphState) -> str:
    """
    auto_fix 이후 분기.
    - terminal_state 설정됨 → END (manual-review-required)
    - last attempt result == "regression" → END (즉시 중단)
    - 그 외 → runtime_validate (재검증)
    """
    if state.get("terminal_state") in ("manual-review-required",):
        return END

    last_attempt = state["fix_attempts"][-1] if state["fix_attempts"] else None
    if last_attempt and last_attempt.result == "pass":
        return "certify"
    if last_attempt and last_attempt.result == "regression":
        return END  # regression 즉시 중단

    return "runtime_validate"


def route_after_certify(state: GraphState) -> str:
    """certify는 항상 END."""
    return END
```

---

## 4. RetryBudgetController 비개선 감지 알고리즘

```python
# src/ddk/services/retry_controller.py

import hashlib
from ddk.models.fix import FixAttempt
from ddk.models.validation import FailureRecord


class RetryBudgetController:

    def __init__(self, max_retries: int = 3, budget_remaining: int | None = None):
        self.max_retries = max_retries
        self._budget = budget_remaining if budget_remaining is not None else max_retries

    def is_non_improving(
        self,
        previous_attempts: list[FixAttempt],
        current_failures: list[FailureRecord],
    ) -> bool:
        """
        다음 4가지 조건 중 2개 이상 충족 시 non-improving으로 판단:
        1. 동일 failure class 집합이 2회 연속 반복
        2. blocker(critical/error) 개수 감소 없음 (2회 연속)
        3. fix attempt result가 "no_change" 2회 연속
        4. 마지막 2번 시도의 context_pack_hash가 동일 (같은 입력 반복)
        """
        if len(previous_attempts) < 2:
            return False

        last = previous_attempts[-1]
        prev = previous_attempts[-2]

        score = 0

        # 조건 1: 동일 failure class 집합 반복
        current_ids = frozenset(f.taxonomy_id for f in current_failures)
        last_ids = frozenset(last.failure_ids)
        prev_ids = frozenset(prev.failure_ids)
        if current_ids == last_ids == prev_ids:
            score += 1

        # 조건 2: blocker count 감소 없음
        current_blockers = sum(
            1 for f in current_failures if f.severity in ("critical", "error")
        )
        last_before = last.validation_delta.get("before", {})
        last_after = last.validation_delta.get("after", {})
        if last_before.get("blocker_count", 0) <= last_after.get("blocker_count", 0):
            score += 1

        # 조건 3: result "no_change" 2회 연속
        if last.result == "no_change" and prev.result == "no_change":
            score += 1

        # 조건 4: 같은 context_pack_hash (동일 입력 반복)
        if last.context_pack_hash == prev.context_pack_hash:
            score += 1

        return score >= 2  # 4개 중 2개 이상 충족
```

---

## 5. GraphState 초기화 헬퍼

```python
# src/ddk/graph/state.py (하단 추가)

def initial_state(case_input: "CaseInput", seed: int | None = None) -> GraphState:
    """그래프 시작 전 초기 state 생성."""
    return GraphState(
        case_id=case_input.case_id,
        case_input=case_input,
        repo_profile=None,
        intent_graph=None,
        generation_plan=None,
        generated_artifacts=None,
        normalization_report=None,
        runtime_validation_report=None,
        visual_regression_report=None,
        fix_attempts=[],
        scorecard=None,
        release_decision=None,
        evidence_pack=None,
        retry_budget_remaining=3,
        current_node="",
        terminal_state=None,
        error_message=None,
        pre_run_checkpoint_ref=None,
        llm_call_records=[],
        total_cost_usd=0.0,
        reproducibility_seed=seed,
    )
```

---

## 7. Design Studio Graph (신규)

Design Studio는 Delivery Loop과 독립된 별도의 `StateGraph`로 구성된다.
아이디어 입력부터 구조화된 인터뷰, 요구사항 추출, 표준 매핑, 문서 생성, 품질 게이트, 패키지 핸드오프까지의 전체 흐름을 관리한다.

### 7.1 DesignStudioState 정의

```python
# src/ddk/graph/design_state.py
from __future__ import annotations
from typing import TypedDict
from ddk.models.design_interview import InterviewTurn
from ddk.models.design_requirement import DesignRequirement
from ddk.models.design_document import DesignDocument
from ddk.models.design_compliance import StandardsComplianceResult
from ddk.models.design_quality import QualityGateScore
from ddk.models.design_package import DesignPackageManifest


class DesignStudioState(TypedDict):
    """Design Studio 그래프의 전체 상태."""
    # ── 입력 ──
    idea: str                                      # 사용자 원본 아이디어
    project_context: str | None                    # 프로젝트 배경 정보
    # ── 인터뷰 ──
    interview_turns: list[InterviewTurn]           # 인터뷰 대화 이력
    interview_complete: bool                       # 인터뷰 완료 여부
    # ── 요구사항 ──
    requirements: list[DesignRequirement]          # 추출된 요구사항
    # ── 표준 매핑 ──
    target_doc_types: list[str]                    # 생성할 문서 유형 목록
    standard_mappings: dict[str, str]              # {doc_type: standard_ref}
    # ── 문서 ──
    documents: list[DesignDocument]                # 생성된 설계문서
    # ── 검증 ──
    compliance_results: list[StandardsComplianceResult]
    quality_gate: QualityGateScore | None          # 품질 게이트 결과
    quality_gate_feedback: str | None              # block 시 피드백 (재생성용)
    # ── 패키지 ──
    package: DesignPackageManifest | None           # 최종 설계 패키지
    # ── 제어 ──
    current_node: str
    error_message: str | None
    llm_call_records: list[str]
    total_cost_usd: float
    synthesis_attempts: int                        # doc_synthesize 재시도 횟수
```

### 7.2 StateGraph 빌드 코드

```python
# src/ddk/graph/design_studio.py

from langgraph.graph import StateGraph, END
from .design_state import DesignStudioState
from .nodes.design import (
    idea_intake_node,
    interview_node,
    requirements_extract_node,
    standards_map_node,
    doc_synthesize_node,
    quality_gate_node,
    package_handoff_node,
)
from .edges_design import route_interview, route_quality_gate


def build_design_studio_graph() -> "CompiledGraph":
    """
    Design Studio 파이프라인 그래프.

    흐름:
    idea_intake → interview → [continue: interview | complete: requirements_extract]
        → standards_map → doc_synthesize → quality_gate
        → [pass/flag: package_handoff | block: doc_synthesize] → END
    """
    design_graph = StateGraph(DesignStudioState)

    # 노드 등록
    design_graph.add_node("idea_intake", idea_intake_node)
    design_graph.add_node("interview", interview_node)
    design_graph.add_node("requirements_extract", requirements_extract_node)
    design_graph.add_node("standards_map", standards_map_node)
    design_graph.add_node("doc_synthesize", doc_synthesize_node)
    design_graph.add_node("quality_gate", quality_gate_node)
    design_graph.add_node("package_handoff", package_handoff_node)

    # 시작점
    design_graph.set_entry_point("idea_intake")

    # 직선 엣지
    design_graph.add_edge("idea_intake", "interview")
    design_graph.add_edge("requirements_extract", "standards_map")
    design_graph.add_edge("standards_map", "doc_synthesize")
    design_graph.add_edge("doc_synthesize", "quality_gate")
    design_graph.add_edge("package_handoff", END)

    # 조건부 엣지: interview 이후
    design_graph.add_conditional_edges(
        "interview",
        route_interview,
        {
            "continue": "interview",             # 추가 질문 필요
            "complete": "requirements_extract",   # 인터뷰 완료
        },
    )

    # 조건부 엣지: quality_gate 이후
    design_graph.add_conditional_edges(
        "quality_gate",
        route_quality_gate,
        {
            "pass": "package_handoff",            # 통과
            "flag": "package_handoff",            # 경고 포함 통과
            "block": "doc_synthesize",            # 재생성 필요
        },
    )

    return design_graph.compile()
```

### 7.3 노드 함수 시그니처

모든 노드는 `DesignStudioState`를 받아 변경된 필드만 dict로 반환한다.

```python
# src/ddk/graph/nodes/design/idea_intake.py
from ddk.graph.design_state import DesignStudioState
from ddk.models.design_interview import InterviewTurn


async def idea_intake_node(state: DesignStudioState) -> dict:
    """
    사용자 아이디어를 수신하고 인터뷰 세션을 초기화.
    시스템 인사 턴을 생성하여 인터뷰 시작.

    Input:  state["idea"], state["project_context"]
    Output: state["interview_turns"] (시스템 인사 턴 추가),
            state["interview_complete"] = False
    """
    greeting = InterviewTurn(
        turn_id="IT-001",
        speaker="system",
        message=f"'{state['idea']}'에 대해 구조화된 요구사항을 도출하겠습니다. "
                "먼저 이 아이디어가 해결하려는 핵심 문제에 대해 설명해 주세요.",
    )
    return {
        "interview_turns": [greeting],
        "interview_complete": False,
        "current_node": "idea_intake",
    }
```

```python
# src/ddk/graph/nodes/design/interview.py
from ddk.graph.design_state import DesignStudioState
from ddk.services.requirements_elicitor import RequirementsElicitorService
from ddk.services.interview_budget import InterviewBudgetController


async def interview_node(state: DesignStudioState) -> dict:
    """
    RequirementsElicitor 프롬프트로 인터뷰 한 턴을 수행.
    InterviewBudgetController가 종료 조건을 판단.

    Input:  state["idea"], state["project_context"], state["interview_turns"]
    Output: state["interview_turns"] (appended — system 턴),
            state["interview_complete"],
            state["llm_call_records"] (appended)
    """
    elicitor = RequirementsElicitorService.from_config()
    controller = InterviewBudgetController()

    result, record = await elicitor.elicit(
        idea=state["idea"],
        context=state.get("project_context"),
        turn_history=state["interview_turns"],
    )

    new_turn = result.to_interview_turn(
        turn_id=f"IT-{len(state['interview_turns']) + 1:03d}",
    )

    is_complete = (
        result.interview_complete
        or result.saturation_signal
        or not controller.should_continue(state["interview_turns"] + [new_turn])
    )

    return {
        "interview_turns": state["interview_turns"] + [new_turn],
        "interview_complete": is_complete,
        "llm_call_records": state["llm_call_records"] + [record.call_id],
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0),
        "current_node": "interview",
    }
```

```python
# src/ddk/graph/nodes/design/requirements_extract.py
from ddk.graph.design_state import DesignStudioState
from ddk.services.requirements_extractor import RequirementsExtractor


async def requirements_extract_node(state: DesignStudioState) -> dict:
    """
    완료된 인터뷰 로그에서 DesignRequirement 목록을 통합 추출.
    턴별 추출 결과를 병합, 중복 제거, MoSCoW 우선순위 확정.

    Input:  state["interview_turns"]
    Output: state["requirements"]
    """
    extractor = RequirementsExtractor()
    requirements = extractor.consolidate(
        turns=state["interview_turns"],
    )
    return {
        "requirements": requirements,
        "current_node": "requirements_extract",
    }
```

```python
# src/ddk/graph/nodes/design/standards_map.py
from ddk.graph.design_state import DesignStudioState
from ddk.services.standards_mapper import StandardsMapper

# 요구사항 특성 → 문서 유형 + 표준 기본 매핑
DEFAULT_STANDARD_MAP: dict[str, str] = {
    "SRS": "IEEE 830",
    "Architecture": "ISO 42010",
    "API": "OpenAPI 3.1",
    "DBSchema": "SQL:2016",
    "Security": "OWASP ASVS 4.0",
    "TestStrategy": "IEEE 829",
    "ImplPlan": "Internal",
    "AIHandoff": "딸깍 Handoff Spec 1.0",
}


async def standards_map_node(state: DesignStudioState) -> dict:
    """
    요구사항 특성에 따라 생성할 문서 유형과 적용 표준을 결정.
    must 요구사항이 많으면 SRS 필수, API 언급 시 OpenAPI 문서 포함 등.

    Input:  state["requirements"]
    Output: state["target_doc_types"], state["standard_mappings"]
    """
    mapper = StandardsMapper(default_map=DEFAULT_STANDARD_MAP)
    doc_types, mappings = mapper.determine(
        requirements=state["requirements"],
    )
    return {
        "target_doc_types": doc_types,
        "standard_mappings": mappings,
        "current_node": "standards_map",
    }
```

```python
# src/ddk/graph/nodes/design/doc_synthesize.py
from ddk.graph.design_state import DesignStudioState
from ddk.services.design_doc_synthesizer import DesignDocSynthesizerService
from ddk.services.compliance_checker import ComplianceChecker


async def doc_synthesize_node(state: DesignStudioState) -> dict:
    """
    DesignDocSynthesizer 프롬프트로 각 문서 유형별 설계문서 생성.
    생성 후 표준 적합성 검증을 즉시 수행.

    Input:  state["requirements"], state["target_doc_types"],
            state["standard_mappings"], state["quality_gate_feedback"]
    Output: state["documents"], state["compliance_results"],
            state["synthesis_attempts"] (incremented)
    """
    synthesizer = DesignDocSynthesizerService.from_config()
    checker = ComplianceChecker()

    documents = []
    compliance_results = []
    records = []

    for doc_type in state["target_doc_types"]:
        standard_ref = state["standard_mappings"][doc_type]
        doc, record = await synthesizer.synthesize(
            requirements=state["requirements"],
            doc_type=doc_type,
            standard_ref=standard_ref,
            project_context=state.get("project_context", ""),
            feedback=state.get("quality_gate_feedback"),
        )
        documents.append(doc)
        records.append(record)

        compliance = checker.check(doc, standard_ref)
        compliance_results.append(compliance)

    new_records = [r.call_id for r in records]
    new_cost = sum(r.cost_usd or 0.0 for r in records)

    return {
        "documents": documents,
        "compliance_results": compliance_results,
        "synthesis_attempts": state.get("synthesis_attempts", 0) + 1,
        "llm_call_records": state["llm_call_records"] + new_records,
        "total_cost_usd": state["total_cost_usd"] + new_cost,
        "current_node": "doc_synthesize",
    }
```

```python
# src/ddk/graph/nodes/design/quality_gate.py
from ddk.graph.design_state import DesignStudioState
from ddk.services.design_quality_gate import DesignQualityGateService


async def quality_gate_node(state: DesignStudioState) -> dict:
    """
    DesignQualityGate 프롬프트로 6축 품질 검증 수행.
    pass/flag/block 판정 결과를 state에 반영.
    block 시 피드백을 quality_gate_feedback에 저장 (재생성용).

    Input:  state["requirements"], state["documents"],
            state["compliance_results"]
    Output: state["quality_gate"], state["quality_gate_feedback"]
    """
    svc = DesignQualityGateService.from_config()
    package_summary = {
        "requirements": [r.model_dump() for r in state["requirements"]],
        "documents": [d.model_dump() for d in state["documents"]],
        "compliance_results": [c.model_dump() for c in state["compliance_results"]],
    }
    score, record = await svc.evaluate(package_summary)

    feedback = None
    if score.verdict == "block":
        feedback = (
            f"품질 게이트 block 판정 (점수: {score.total_score}/30).\n"
            f"Hard blocks: {'; '.join(score.hard_blocks)}\n"
            f"Recommendations: {'; '.join(score.recommendations)}"
        )

    return {
        "quality_gate": score,
        "quality_gate_feedback": feedback,
        "llm_call_records": state["llm_call_records"] + [record.call_id],
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0),
        "current_node": "quality_gate",
    }
```

```python
# src/ddk/graph/nodes/design/package_handoff.py
from datetime import datetime, timezone
from ddk.graph.design_state import DesignStudioState
from ddk.models.design_package import DesignPackageManifest


async def package_handoff_node(state: DesignStudioState) -> dict:
    """
    모든 산출물을 DesignPackageManifest로 패키징.
    Delivery Loop 또는 외부 시스템으로 핸드오프 준비 완료 상태를 생성.

    Input:  모든 state 필드
    Output: state["package"]
    """
    package = DesignPackageManifest(
        package_id=f"DP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        project_name=state["idea"][:100],
        requirements=state["requirements"],
        documents=state["documents"],
        compliance_results=state["compliance_results"],
        quality_gate=state["quality_gate"],
        interview_log=state["interview_turns"],
        created_at=datetime.now(timezone.utc),
    )
    return {
        "package": package,
        "current_node": "package_handoff",
    }
```

### 7.4 Edge 조건 함수

```python
# src/ddk/graph/edges_design.py

from .design_state import DesignStudioState


def route_interview(state: DesignStudioState) -> str:
    """
    인터뷰 완료 여부에 따라 분기.
    - interview_complete=True → "complete" (requirements_extract로 진행)
    - interview_complete=False → "continue" (interview 루프 반복)
    """
    if state.get("interview_complete"):
        return "complete"
    return "continue"


def route_quality_gate(state: DesignStudioState) -> str:
    """
    품질 게이트 verdict에 따라 분기.
    - "pass" → package_handoff (통과)
    - "flag" → package_handoff (경고 포함 통과)
    - "block" → doc_synthesize (재생성, 최대 3회)

    synthesis_attempts ≥ 3이면 강제 flag로 전환하여 무한 루프 방지.
    """
    qg = state.get("quality_gate")
    if not qg:
        return "block"

    if qg.verdict == "block" and state.get("synthesis_attempts", 0) >= 3:
        return "flag"  # 재시도 초과 → 경고 포함 강제 통과

    return qg.verdict  # "pass" | "flag" | "block"
```

### 7.5 InterviewBudgetController

```python
# src/ddk/services/interview_budget.py

from ddk.models.design_interview import InterviewTurn


class InterviewBudgetController:
    """
    인터뷰 턴 수 관리 — 최대 20턴, 포화 감지 시 조기 종료.

    포화(saturation)란 최근 N턴 동안 새로운 요구사항이
    전혀 추출되지 않는 상태를 의미한다.
    """

    MAX_TURNS: int = 20
    SATURATION_WINDOW: int = 3  # 최근 N턴 동안 새 REQ 없으면 포화

    def __init__(self, max_turns: int | None = None):
        self.max_turns = max_turns or self.MAX_TURNS

    def should_continue(self, turns: list[InterviewTurn]) -> bool:
        """
        인터뷰 계속 여부 판단.

        종료 조건 (하나라도 충족 시 False):
        1. 턴 수가 max_turns 이상
        2. 최근 SATURATION_WINDOW 턴 동안 새 요구사항 추출 없음 (포화)

        Returns:
            True = 계속 진행, False = 인터뷰 종료
        """
        # 조건 1: 턴 수 초과
        if len(turns) >= self.max_turns:
            return False

        # 조건 2: 포화 감지
        if len(turns) >= self.SATURATION_WINDOW:
            recent = turns[-self.SATURATION_WINDOW:]
            if all(len(t.extracted_requirements) == 0 for t in recent):
                return False

        return True

    def remaining_turns(self, current_turn_count: int) -> int:
        """남은 턴 수 계산."""
        return max(0, self.max_turns - current_turn_count)
```

### 7.6 초기 State 헬퍼

```python
# src/ddk/graph/design_state.py (하단 추가)

def initial_design_state(idea: str, project_context: str | None = None) -> DesignStudioState:
    """Design Studio 그래프 시작 전 초기 state 생성."""
    return DesignStudioState(
        idea=idea,
        project_context=project_context,
        interview_turns=[],
        interview_complete=False,
        requirements=[],
        target_doc_types=[],
        standard_mappings={},
        documents=[],
        compliance_results=[],
        quality_gate=None,
        quality_gate_feedback=None,
        package=None,
        current_node="",
        error_message=None,
        llm_call_records=[],
        total_cost_usd=0.0,
        synthesis_attempts=0,
    )
```

### 7.7 Design Studio Node 구현 상세

> Phase 6 구현자가 추론 없이 착수할 수 있도록 각 노드의 입출력과 핵심 로직을 명세.

#### idea_intake 노드

```python
# src/ddk/nodes/design_studio/idea_intake.py

from ddk.models.design_studio import DesignStudioState

async def node_idea_intake(state: DesignStudioState) -> DesignStudioState:
    """사용자 아이디어를 수집하고 초기 컨텍스트를 구성."""
    # 입력: state.user_idea (str), state.project_context (optional)
    # 출력: state.idea_summary, state.interview_questions_remaining

    idea = state.user_idea
    if not idea or len(idea.strip()) < 10:
        state.status = "blocked"
        state.block_reason = "아이디어가 너무 짧음 (최소 10자)"
        return state

    # LLM 호출: 아이디어 → 구조화된 요약 + 초기 질문 목록 생성
    response = await state.llm.complete_structured(
        messages=[
            Message(role="system", content=IDEA_INTAKE_SYSTEM_PROMPT),
            Message(role="user", content=f"아이디어: {idea}"),
        ],
        config=state.llm_config,
        output_schema=IdeaIntakeSummary,
    )
    summary = IdeaIntakeSummary.model_validate(response.raw)
    state.idea_summary = summary.summary
    state.interview_questions = summary.initial_questions
    state.interview_turn_count = 0
    state.max_interview_turns = 5  # from InterviewBudgetController
    return state
```

#### interview 노드

```python
# src/ddk/nodes/design_studio/interview.py

async def node_interview(state: DesignStudioState) -> DesignStudioState:
    """사용자와 대화형 인터뷰로 요구사항 심화."""
    # 입력: state.interview_questions, state.interview_history
    # 출력: state.interview_history (appended), state.interview_turn_count++

    if state.interview_turn_count >= state.max_interview_turns:
        return state  # 예산 소진 → edge에서 requirements_extract로 라우팅

    current_question = state.interview_questions[0] if state.interview_questions else None
    if current_question is None:
        return state  # 질문 소진

    # 사용자 응답 대기 (CLI에서 interactive input)
    user_answer = await state.get_user_input(prompt=current_question)

    state.interview_history.append(InterviewTurn(
        turn_number=state.interview_turn_count,
        question=current_question,
        answer=user_answer,
        extracted_facts=[],  # LLM이 다음 단계에서 추출
    ))
    state.interview_turn_count += 1
    state.interview_questions.pop(0)

    # LLM으로 후속 질문 생성 (필요 시)
    if state.interview_turn_count < state.max_interview_turns:
        followup = await state.llm.complete_structured(
            messages=_build_followup_messages(state),
            config=state.llm_config,
            output_schema=FollowUpQuestions,
        )
        new_questions = FollowUpQuestions.model_validate(followup.raw)
        state.interview_questions.extend(new_questions.questions[:3])

    return state
```

#### requirements_extract 노드

```python
# src/ddk/nodes/design_studio/requirements_extract.py

async def node_requirements_extract(state: DesignStudioState) -> DesignStudioState:
    """인터뷰 결과에서 구조화된 요구사항 목록 추출."""
    # 입력: state.interview_history, state.idea_summary
    # 출력: state.requirements (list[DesignRequirement])

    context = _compile_interview_context(state.interview_history, state.idea_summary)

    response = await state.llm.complete_structured(
        messages=[
            Message(role="system", content=REQUIREMENTS_ELICITOR_SYSTEM_PROMPT),
            Message(role="user", content=context),
        ],
        config=state.llm_config,
        output_schema=RequirementsList,
    )
    result = RequirementsList.model_validate(response.raw)

    state.requirements = [
        DesignRequirement(
            req_id=f"DR-{i+1:03d}",
            title=r.title,
            description=r.description,
            priority=r.priority,
            acceptance_criteria=r.acceptance_criteria,
            source_turn=r.source_turn,
        )
        for i, r in enumerate(result.requirements)
    ]
    return state
```

#### standards_map 노드

```python
# src/ddk/nodes/design_studio/standards_map.py

async def node_standards_map(state: DesignStudioState) -> DesignStudioState:
    """추출된 요구사항을 국제표준 조항에 매핑."""
    # 입력: state.requirements
    # 출력: state.standards_results (list[StandardsComplianceResult])

    req_summaries = [f"{r.req_id}: {r.title} — {r.description[:100]}" for r in state.requirements]

    response = await state.llm.complete_structured(
        messages=[
            Message(role="system", content=STANDARDS_MAPPER_SYSTEM_PROMPT),
            Message(role="user", content="\n".join(req_summaries)),
        ],
        config=state.llm_config,
        output_schema=StandardsMappingResult,
    )
    result = StandardsMappingResult.model_validate(response.raw)

    state.standards_results = [
        StandardsComplianceResult(
            standard_id=m.standard_id,
            clause=m.clause,
            requirement_ids=m.requirement_ids,
            compliance_status="mapped",
            evidence_description=m.rationale,
        )
        for m in result.mappings
    ]
    return state
```

#### doc_synthesize 노드

```python
# src/ddk/nodes/design_studio/doc_synthesize.py

async def node_doc_synthesize(state: DesignStudioState) -> DesignStudioState:
    """요구사항 + 표준 매핑 → 설계문서 패키지 생성."""
    # 입력: state.requirements, state.standards_results, state.idea_summary
    # 출력: state.design_document (DesignDocument)

    context = _compile_synthesis_context(
        idea=state.idea_summary,
        requirements=state.requirements,
        standards=state.standards_results,
    )

    response = await state.llm.complete_structured(
        messages=[
            Message(role="system", content=DESIGN_DOC_SYNTHESIZER_SYSTEM_PROMPT),
            Message(role="user", content=context),
        ],
        config=LLMCallConfig(
            model=state.llm_config.model,
            temperature=0.0,
            max_tokens=8192,  # 긴 문서 생성
        ),
        output_schema=DesignDocument,
    )
    state.design_document = DesignDocument.model_validate(response.raw)
    return state
```

#### quality_gate 노드

```python
# src/ddk/nodes/design_studio/quality_gate.py

async def node_quality_gate(state: DesignStudioState) -> DesignStudioState:
    """생성된 설계문서의 architect-grade 품질 평가."""
    # 입력: state.design_document
    # 출력: state.quality_score (QualityGateScore)

    doc_text = state.design_document.to_review_text()

    response = await state.llm.complete_structured(
        messages=[
            Message(role="system", content=DESIGN_QUALITY_GATE_SYSTEM_PROMPT),
            Message(role="user", content=doc_text),
        ],
        config=state.llm_config,
        output_schema=QualityGateScore,
    )
    state.quality_score = QualityGateScore.model_validate(response.raw)

    # Hard block 검사
    if state.quality_score.verdict == "block":
        state.status = "quality-blocked"
        state.block_reason = f"Quality gate: {state.quality_score.total}/30, verdict=block"
    elif state.quality_score.verdict == "flag":
        state.status = "quality-flagged"

    return state
```

#### package_handoff 노드

```python
# src/ddk/nodes/design_studio/package_handoff.py

async def node_package_handoff(state: DesignStudioState) -> DesignStudioState:
    """최종 설계 패키지 조립 및 artifact 저장."""
    # 입력: state.design_document, state.quality_score, state.requirements, state.standards_results
    # 출력: state.package_manifest (DesignPackageManifest)

    manifest = DesignPackageManifest(
        package_id=f"PKG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        created_at=datetime.now(timezone.utc),
        idea_summary=state.idea_summary,
        requirement_count=len(state.requirements),
        standards_mapped=len(state.standards_results),
        quality_verdict=state.quality_score.verdict,
        quality_total=state.quality_score.total,
        documents=[
            DocumentEntry(
                title=state.design_document.title,
                version=state.design_document.version,
                sections=len(state.design_document.sections),
            )
        ],
    )
    state.package_manifest = manifest

    # Artifact 저장
    await _save_package_artifacts(
        workspace=state.workspace_dir,
        document=state.design_document,
        manifest=manifest,
        requirements=state.requirements,
        standards=state.standards_results,
        quality=state.quality_score,
    )

    state.status = "completed"
    return state
```

### Edge Conditions 상세

```python
# src/ddk/nodes/design_studio/edges.py

def should_continue_interview(state: DesignStudioState) -> str:
    """인터뷰 계속 여부 결정."""
    if state.interview_turn_count >= state.max_interview_turns:
        return "requirements_extract"  # 예산 소진
    if not state.interview_questions:
        return "requirements_extract"  # 질문 소진
    return "interview"  # 계속

def should_pass_quality(state: DesignStudioState) -> str:
    """품질 게이트 통과 여부 결정."""
    if state.quality_score is None:
        return "quality_gate"  # 아직 평가 안 됨
    if state.quality_score.verdict == "block":
        return "doc_synthesize"  # 재생성 (최대 1회)
    return "package_handoff"  # pass 또는 flag
```

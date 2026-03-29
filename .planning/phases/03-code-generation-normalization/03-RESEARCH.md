# Phase 3: Code Generation & Normalization — Research

**Researched:** 2025-07-28
**Domain:** LLM-driven code generation + rule-based/LLM normalization inside LangGraph
**Confidence:** HIGH (all decisions derived from existing design docs + Phase 2 verified codebase)

---

<user_constraints>
## User Constraints (from Phase 2 CONTEXT.md — locked decisions carry forward)

### Locked Decisions (inherited + Phase 3-specific)
- **D-05 (inherited):** `src/ddk/services/` 레이어 분리. 노드는 상태 읽기·서비스 호출·상태 쓰기만 담당하며 로직이 없다 (Thin Adapter 패턴).
- **D-06 (inherited):** 모든 서비스 단위 테스트는 `FakeLLMAdapter` 사용. `@pytest.mark.integration` 마커로 실제 API 통합 테스트 선택적 추가.
- **D-08 (inherited + extended):** Phase 2 완료 시 5노드 연결. Phase 3에서 `generate`, `normalize` 노드를 이어 붙여 7노드 파이프라인 완성.
- **Architecture (ADR-010):** LangGraph StateGraph, context_schema DI 패턴.
- **Models (Phase 1):** 40+ Pydantic v2 모델 이미 구현됨. 새 모델 추가 시 `DDKBaseModel` 상속.
- **LLM:** `complete_structured()` tool_use 방식 강제 (16-prompt-design.md 원칙 §1).
- **Reproducibility:** temperature=0.0, seed 고정으로 결정론적 출력 (16-prompt-design.md 원칙 §3).
- **Cost:** P0 단일 케이스 ≤ $0.10. Phase 3 LLM 비용 예산: ≤ $0.04/케이스 (generate=sonnet, normalize=haiku).

### Agent's Discretion
- CodeGenerator 내부 헬퍼 메서드 분리 방식
- FakeLLM 키 전략 세부 (시스템 프롬프트 첫 단어 vs 다른 방식)
- OutputNormalizer LLM 호출 전략 (파일별 vs 배치)
- `conftest.py` fixture 재사용 패턴 (Phase 2 패턴 따름)

### Deferred Ideas (OUT OF SCOPE)
- 병렬 노드 생성 (asyncio.gather로 각 GenerationNode를 동시에 처리) — Phase 5 최적화
- 실제 TypeScript 컴파일 검증 (Phase 4 VALID-01 범위)
- Multi-provider LLM fallback — Phase 5 이후
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CODEGEN-01 | CodeGenerator 서비스: GenerationPlan → GeneratedArtifactSet (컴포넌트/페이지 파일 + 파일 맵 + 생성 트레이스) | 16-prompt-design.md §4 CodeGenerator 프롬프트 확인; 노드별 LLM 호출 설계; FakeLLM 키 충돌 해결책 포함 |
| CODEGEN-02 | OutputNormalizer 서비스: RepoProfile 기반 정규화 → NormalizationReport | 16-prompt-design.md §6 ConventionNormalizer 프롬프트 확인; haiku 모델로 비용 최적화; 모델 필드 정렬 필요 |
</phase_requirements>

---

## Summary

Phase 3는 Phase 2가 생성한 `GenerationPlan`을 실제 React/TypeScript 파일로 변환하고, 생성된 코드를 타겟 레포 규칙에 맞게 정규화하는 단계다. 이를 위해 `CodeGenerator` 서비스와 `OutputNormalizer` 서비스를 구현하고, 각각 `generate_node`, `normalize_node`로 감싸 LangGraph 그래프를 5노드에서 7노드로 확장한다.

**핵심 발견 사항:** (1) 설계 문서(`12-data-models.md`)의 `GeneratedArtifactSet`/`NormalizationReport` 필드 정의가 Phase 1에서 구현된 실제 모델과 불일치한다. Wave 0에서 모델을 설계 문서 기준으로 정렬해야 이후 Phase 4·5에서 혼선을 방지할 수 있다. (2) `FakeLLMAdapter`의 key extraction(시스템 프롬프트 첫 단어)이 `SemanticIntentExtractor`("You...")와 `CodeGenerator`("You...")를 충돌시킨다 — E2E 테스트 전에 반드시 해결해야 한다.

**Primary recommendation:** Wave 0에서 모델 정렬 → Wave 1에서 CodeGenerator → Wave 2에서 OutputNormalizer → Wave 3에서 7노드 그래프 조립 + E2E 순서로 진행. OutputNormalizer는 CodeGenerator의 출력 구조에 의존하므로 엄격히 순차 진행한다.

---

## Standard Stack

### Core (기존 Phase 1/2에서 확립)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| LangGraph | (pyproject.toml 기준) | StateGraph orchestration | ADR-010 확정 |
| Pydantic v2 | ^2.x | 모든 데이터 모델 | Phase 1 전체 구현됨, DDKBaseModel 기반 |
| anthropic SDK | (pyproject.toml 기준) | Claude API (`ClaudeAdapter`) | Phase 2에서 ClaudeAdapter 완전 구현됨 |
| pytest-asyncio | (pyproject.toml 기준) | 비동기 테스트 | Phase 2 패턴 확립 |
| structlog | (pyproject.toml 기준) | 구조화 로깅 | INFRA-06 구현됨 |

### LLM Models for Phase 3
| Call | Model | Reason |
|------|-------|--------|
| CodeGenerator (generate) | `claude-3-5-sonnet-20241022` | 16-prompt-design.md §4 명시, 고품질 코드 생성 필요 |
| OutputNormalizer (normalize) | `claude-3-haiku-20240307` | 16-prompt-design.md §6 명시, 규칙 검사는 저렴한 모델로 충분 |

**비용 추정 (케이스당):**
- CodeGenerator: 5노드 × ~4,800 tokens × $3/$15 per 1M = ~$0.02 (3노드 기준 ~$0.012)
- OutputNormalizer: 1 batch call × ~6,000 tokens × $0.25/$1.25 per 1M = ~$0.001
- Phase 3 예상 추가 비용: ~$0.013–$0.022 (전체 $0.10 예산 내 여유)

---

## Architecture Patterns

### Recommended Project Structure (Phase 3 추가 파일)
```
src/ddk/
├── services/
│   ├── code_generator.py          # CODEGEN-01 핵심 서비스
│   └── output_normalizer.py       # CODEGEN-02 핵심 서비스
├── graph/
│   └── nodes/
│       ├── generate.py            # thin adapter → CodeGenerator
│       └── normalize.py           # thin adapter → OutputNormalizer
│
tests/
├── unit/
│   └── services/
│       ├── test_code_generator.py
│       └── test_output_normalizer.py
└── integration/
    └── test_generation_pipeline.py  # 7-node E2E (확장)
```

### Pattern 1: CodeGenerator — Node-by-Node LLM 호출
**What:** `execution_order`를 순서대로 순회하며 각 `GenerationNode`에 대해 별도 LLM 호출. 각 호출은 해당 노드의 컨텍스트만 집중해서 전달 (12k token 예산).
**When to use:** 항상 (설계 문서 §4에 명시적으로 "노드별 개별 LLM 호출").
**Example:**
```python
# Source: docs/design/16-prompt-design.md §4
# src/ddk/services/code_generator.py

_SYSTEM_PROMPT = """Generate production-quality React/TypeScript code for a single file.

## Code Quality Rules
1. Use TypeScript with strict mode.
2. All props must have explicit types.
3. No `any` types.
4. Use the project's CSS approach as specified.
5. Import from existing components when available.
6. Component file structure:
   - imports (external libraries first, then internal)
   - type definitions
   - main component
   - export default
7. No placeholder comments like "// TODO: implement this".
8. The generated file must be complete and immediately functional.

## Response Format
Output structured JSON with files array."""

# KEY: starts with "Generate" (not "You") — avoids FakeLLM key collision with SemanticIntentExtractor

class CodeGenerator:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=4096,
        )

    async def generate_all(
        self,
        plan: GenerationPlan,
        repo_profile: RepoProfile,
        intent_graph: IntentGraph,
        prompt: str,
    ) -> GeneratedArtifactSet:
        all_files: list[GeneratedFile] = []
        trace_entries: list[str] = []
        total_tokens = 0

        node_map = {n.id: n for n in plan.nodes}
        for node_id in plan.execution_order:
            node = node_map[node_id]
            node_output = await self._generate_node(node, repo_profile, intent_graph, prompt)
            all_files.extend(node_output.files)
            trace_entries.append(f"{node_id}:{node.target_path}")
            # accumulate tokens from response

        file_map = {f.path: f.content for f in all_files}
        return GeneratedArtifactSet(
            case_id=plan.case_id,
            files=all_files,
            file_map=file_map,
            generation_trace=trace_entries,
            total_tokens_used=total_tokens,
        )
```

### Pattern 2: GeneratedNodeOutput — Per-node 구조화 출력 스키마
**What:** 단일 `GenerationNode` 처리 결과를 담는 내부 Pydantic 모델. `complete_structured(output_schema=GeneratedNodeOutput)` 호출 시 스키마 강제.
**When to use:** CodeGenerator 내부에서만 사용 (public API는 `GeneratedArtifactSet`).
**Example:**
```python
# src/ddk/services/code_generator.py (내부 모델)
from pydantic import BaseModel

class _GeneratedNodeOutput(DDKBaseModel):
    """Per-node LLM output schema. Used only internally by CodeGenerator."""
    files: list[GeneratedFile]
    entry_point: str | None = None
    component_exports: list[str] = []
```

### Pattern 3: OutputNormalizer — Batch LLM 호출
**What:** 생성된 모든 파일을 한 번의 LLM 호출에서 정규화. 각 파일에서 위반 사항 추출 → `NormalizationReport` 생성 → 코드 수정 적용.
**When to use:** CodeGenerator 완료 직후 (generate → normalize 엣지).
**Example:**
```python
# Source: docs/design/16-prompt-design.md §6
# src/ddk/services/output_normalizer.py

_SYSTEM_PROMPT = """Normalize convention violations for repository code.

Review generated code and output a NormalizationReport listing convention fixes.

Focus on:
1. Component naming: PascalCase vs kebab-case per NamingRules
2. File placement: components in correct directory per FileLayoutRules
3. Import ordering: external libraries before internal
4. Design token usage: replace hardcoded colors/spacing with token references
5. Primitive reuse: use existing components if functionally equivalent

Do NOT change business logic or component structure.
Do NOT fix TypeScript errors."""

# KEY: starts with "Normalize" — unique FakeLLM key

class OutputNormalizer:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-haiku-20240307",  # 저렴한 모델 (규칙 검사)
            temperature=0.0,
            max_tokens=2048,
        )

    async def normalize(
        self,
        artifacts: GeneratedArtifactSet,
        repo_profile: RepoProfile,
    ) -> tuple[NormalizationReport, GeneratedArtifactSet]:
        ...
```

### Pattern 4: Thin Node Adapter (D-05 준수)
**What:** `generate_node`, `normalize_node`는 Phase 2 노드와 동일한 패턴. ServiceContainer에서 서비스 추출 → 호출 → 상태 반환.
**Example:**
```python
# Source: D-05 결정, Phase 2 노드 패턴 준용
# src/ddk/graph/nodes/generate.py

async def generate_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    if llm is None:
        return {"terminal_state": "manual-review-required", "error_message": "No LLM in container"}

    generator = CodeGenerator(llm=llm)
    artifacts = await generator.generate_all(
        plan=state["generation_plan"],
        repo_profile=state["repo_profile"],
        intent_graph=state["intent_graph"],
        prompt=state["case_input"].prompt,
    )
    return {
        "generated_artifacts": artifacts,
        "current_node": "generate",
        "total_cost_usd": state.get("total_cost_usd", 0.0) + artifacts.total_tokens_used * 0.0,
        # 실제 cost는 LLMResponse.cost_usd에서 누적
    }

# src/ddk/graph/nodes/normalize.py

async def normalize_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    container: ServiceContainer | None = kwargs.get("context")
    llm = container.llm if container is not None else None
    normalizer = OutputNormalizer(llm=llm)
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

### Pattern 5: Graph Extension (D-08 연장)
```python
# src/ddk/graph/builder.py — Phase 3 완료 후

from ddk.graph.nodes.generate import generate_node
from ddk.graph.nodes.normalize import normalize_node

workflow.add_node("generate", node_wrapper(generate_node))
workflow.add_node("normalize", node_wrapper(normalize_node))

# 기존 plan → END를 plan → generate → normalize → END로 교체
workflow.add_edge("plan", "generate")
workflow.add_edge("generate", "normalize")
workflow.add_edge("normalize", END)
# (기존 workflow.add_edge("plan", END) 삭제)
```

### Anti-Patterns to Avoid
- **Batch all nodes into one LLM call:** 설계 문서가 명시적으로 "노드별 개별 LLM 호출"을 지정. 배치는 컨텍스트 혼선 + 재현성 저하.
- **AST 기반 normalizer:** 설계 문서(§6)가 LLM(haiku) 기반 normalizer를 명시. Python에서 TypeScript AST 처리는 외부 의존성 복잡도를 크게 늘림.
- **`CodeGenerator.from_config()` 패턴:** 설계 문서(19-langgraph-builder.md)에 나오지만 D-05의 DI 패턴과 충돌. D-05가 locked 결정이므로 ServiceContainer DI 방식 사용.
- **FakeLLM 키 충돌 방치:** SemanticIntentExtractor("You are an expert UI analyst") 와 CodeGenerator("You are an expert React/TypeScript developer") 모두 첫 단어가 "you". **반드시 CodeGenerator 시스템 프롬프트를 "Generate"로 시작하도록 변경**.
- **NormalizationReport 필드 불일치 무시:** 기존 구현 모델을 그대로 쓰면 Phase 4·5에서 `convention_fixes`, `drift_score_*` 누락으로 연쇄 문제 발생.
- **`state["list"].append()` 직접 뮤테이션:** LangGraph 불변 상태 패턴 필수. 항상 새 list 반환.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TypeScript 구문 검증 | 자체 TS parser | Phase 4 BuildRunnerAdapter + git worktree | Phase 3 범위 아님; TypeScript 파서는 언어 바인딩 복잡도 높음 |
| Import 정렬 | 커스텀 AST 분석기 | LLM(haiku) normalizer | 설계 문서가 명시적으로 LLM 방식 선택; AST는 외부 의존성 필요 |
| 코드 템플릿 엔진 | Jinja2/Mako 템플릿 | LLM structured output | 동적 컴포넌트 구조는 템플릿으로 표현 불가 |
| 디자인 토큰 치환 | 정규식 문자열 치환 | LLM normalizer (문맥 인식) | 같은 색상값이 다른 목적(배경 vs 텍스트)에 쓰이면 정규식이 오·탈락 |
| JSON Schema validation | 자체 validator | Pydantic `model_validate()` | Phase 1에서 이미 모든 모델 구현됨 |

**Key insight:** Phase 3의 "코드 생성"과 "정규화"는 모두 LLM 호출로 처리한다. 설계 문서(16-prompt-design.md)가 두 단계의 프롬프트를 완전히 명시하고 있으므로 직접 구현의 여지가 없다.

---

## Critical Gap: 모델 필드 불일치

### Gap 1: GeneratedArtifactSet

| Field | Design Doc (12-data-models.md) | Existing Code (generation.py) | Action |
|-------|-------------------------------|-------------------------------|--------|
| `files` | `list[GeneratedFile]` | `list[GeneratedFile]` | ✓ 일치 |
| `file_map` | 없음 | `dict[str, str]` | Wave 0에서 확인 |
| `generation_trace` | 없음 (→ `trace: dict`) | `list[str]` | Wave 0에서 정렬 |
| `total_tokens_used` | 없음 | `int` | Phase 3 편의 필드로 유지 가능 |
| `changed_paths` | `list[str]` | 없음 | Wave 0에서 추가 or 서비스에서 `file_map`으로 대체 |
| `schema_version` | `"1.0"` | 없음 | Wave 0에서 추가 |

| GeneratedFile field | Design Doc | Existing Code | Action |
|---------------------|-----------|---------------|--------|
| `is_new` | `bool` | 없음 | Wave 0에서 추가 |
| `original_content` | `str \| None` | 없음 | Wave 0에서 추가 |
| `language` | 없음 | `Literal[...]` | 유지 (유용) |
| `source_node_id` | 없음 | `str` | 유지 (traceability) |

### Gap 2: NormalizationReport

| Field | Design Doc (12-data-models.md) | Existing Code (normalization.py) | Action |
|-------|-------------------------------|----------------------------------|--------|
| `convention_fixes` | `list[ConventionFix]` | `fixes: list[ConventionFix]` | Wave 0: 필드명 정렬 |
| `drift_score_before` | `float` | 없음 | Wave 0: 추가 필수 |
| `drift_score_after` | `float` | 없음 | Wave 0: 추가 필수 |
| `unresolved_drift` | `list[str]` | 없음 | Wave 0: 추가 |
| `files_modified` | 없음 | `list[str]` | 유지 가능 |
| `skipped_rules` | 없음 | `list[str]` | 유지 가능 |
| `duration_ms` | 없음 | `int` | 유지 가능 |

| ConventionFix field | Design Doc | Existing Code | Action |
|--------------------|-----------|---------------|--------|
| `fix_type` | `Literal["naming", "import_order", ...]` | 없음 (`rule_id: str` 사용) | Wave 0: `fix_type` 추가, `rule_id` 호환 유지 |
| `severity` | `Literal["must-fix", "should-fix", "nice-to-have"]` | 없음 | Wave 0: 추가 필수 |
| `before`/`after` | `str \| None` | `before_snippet/after_snippet: str` | Wave 0: 설계 문서 이름으로 정렬 |

**Resolution Strategy:** Wave 0에서 기존 모델에 설계 문서 필드를 추가(additive). 기존 필드는 유지. `NormalizationReport.drift_score_before/after`는 `compute_drift_score()` 정적 메서드로 계산. 이 변경은 Phase 1/2 테스트 파괴 없이 가능 (optional 필드로 추가, default 값 제공).

---

## FakeLLM Key Collision Resolution

### 문제
```python
# SemanticIntentExtractor (Phase 2)
_SYSTEM_PROMPT = "You are an expert UI analyst..."
# → FakeLLMAdapter key: "you"

# CodeGenerator (Phase 3, 설계 문서 그대로)
_SYSTEM_PROMPT = "You are an expert React/TypeScript developer..."
# → FakeLLMAdapter key: "you"  ← 충돌!
```

### 해결책: CodeGenerator 시스템 프롬프트 첫 단어 변경
```python
# src/ddk/services/code_generator.py
_SYSTEM_PROMPT = """Generate production-quality React/TypeScript code for a single file.
# (설계 문서 내용 유지, 첫 단어만 "Generate"로 변경)
...
"""
# → FakeLLMAdapter key: "generate"  ← 충돌 없음
```

### 6-node E2E 테스트 FakeLLM 응답 키 맵
```python
FakeLLMAdapter(responses={
    "you":        _INTENT_GRAPH_RESPONSE,      # SemanticIntentExtractor
    "analyze":    _DESIGN_SYSTEM_RESPONSE,     # DesignSystemInferencer
    "senior":     _GENERATION_PLAN_RESPONSE,   # GenerationPlanner
    "generate":   _GENERATED_NODE_RESPONSE,    # CodeGenerator ← NEW
    "normalize":  _NORMALIZATION_RESPONSE,     # OutputNormalizer ← NEW
})
```

---

## Common Pitfalls

### Pitfall 1: FakeLLM Key Collision
**What goes wrong:** E2E 테스트에서 `CodeGenerator`가 SemanticIntentExtractor용 IntentGraph JSON을 받아 파싱 실패.
**Why it happens:** 두 서비스 모두 시스템 프롬프트가 "You"로 시작 → 같은 FakeLLM 키 → 잘못된 JSON 반환.
**How to avoid:** CodeGenerator 시스템 프롬프트를 "Generate"로 시작하도록 수정.
**Warning signs:** `generate_all()` 단위 테스트에서 `GeneratedNodeOutput.model_validate()` `ValidationError`.

### Pitfall 2: GenerationNode이 없는 plan에 대한 처리
**What goes wrong:** `GenerationPlan.execution_order = []`이면 `generate_all()`이 빈 `GeneratedArtifactSet`을 반환 → `normalize_node`가 빈 파일 목록에 LLM 호출 낭비.
**Why it happens:** GenerationPlanner가 FakeLLM에서 빈 plan을 반환할 때.
**How to avoid:** `generate_all()`에 early return: `if not plan.execution_order: return empty artifact set`. `normalize`도 빈 artifacts 방어 처리.
**Warning signs:** 테스트에서 normalize가 빈 report를 반환하고 `duration_ms=0`.

### Pitfall 3: NormalizationReport drift_score 계산 누락
**What goes wrong:** `drift_score_before`/`drift_score_after` 필드가 0으로 고정되어 Phase 4 auto-fix loop의 우선순위 결정 로직이 작동 안 함.
**Why it happens:** Wave 0에서 모델 필드 추가 후 서비스가 `compute_drift_score()`를 호출 안 함.
**How to avoid:** `OutputNormalizer.normalize()` 반환 전에 반드시 `NormalizationReport.compute_drift_score(fixes)` 계산하여 두 필드 설정.
**Warning signs:** `normalization_report.drift_score_before == 0.0` and `len(normalization_report.convention_fixes) > 0`.

### Pitfall 4: generated_artifacts가 None일 때 normalize_node 패닉
**What goes wrong:** `generate_node`에서 에러 발생 시 `generated_artifacts=None` 상태로 `normalize_node` 진입 → `AttributeError`.
**Why it happens:** `node_wrapper`가 에러를 잡아 `terminal_state="manual-review-required"` 반환하지만, LangGraph 엣지가 항상 `normalize`로 향하는 경우.
**How to avoid:** `normalize_node` 시작 시 `if state.get("generated_artifacts") is None` 방어 처리. Phase 4에서 conditional edge 추가 예정이지만 Phase 3에서도 None 방어는 필수.
**Warning signs:** `test_normalize_with_no_artifacts`가 없으면 테스트 커버리지 누락.

### Pitfall 5: 모델 필드 추가 후 기존 테스트 파괴
**What goes wrong:** Wave 0에서 `NormalizationReport`에 `drift_score_before/after: float` 추가 시 기존 `test_output_models.py`의 `NormalizationReport()` 생성자가 필수 필드 누락으로 실패.
**Why it happens:** Pydantic v2는 required 필드(default 없음)에 값을 안 주면 `ValidationError`.
**How to avoid:** 신규 필드는 `float = 0.0` 기본값 부여. 또는 `Field(default=0.0, ge=0.0, le=10.0)`. 설계 문서의 `compute_drift_score()`가 명시적으로 계산 후 설정하는 패턴이므로 기본값 0.0은 적절.
**Warning signs:** `uv run pytest tests/unit/models/test_output_models.py -x` 실패.

### Pitfall 6: `state["list"] + new_records` 불변 패턴 위반
**What goes wrong:** `state["llm_call_records"].append(record_id)` 직접 뮤테이션 → LangGraph 상태 오염.
**Why it happens:** Phase 2 노드 코드를 참고할 때 `state["list"]` 직접 접근 패턴을 잘못 따라함.
**How to avoid:** 항상 `"llm_call_records": state["llm_call_records"] + [new_id]` 패턴. Phase 2 통합 테스트 참고.
**Warning signs:** `contract/test_state_no_mutation.py` 실패.

---

## Code Examples

### CodeGenerator 단위 테스트 패턴
```python
# Source: Phase 2 test_design_system_inferencer.py 패턴 준용
# tests/unit/services/test_code_generator.py

import json
import pytest
from ddk.services.code_generator import CodeGenerator
from ddk.models.generation import GenerationPlan, GenerationNode, GeneratedArtifactSet
from ddk.models.repo import RepoProfile
from ddk.models.intent import IntentGraph
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

_FAKE_NODE_RESPONSE = json.dumps({
    "files": [
        {
            "path": "src/components/Button/Button.tsx",
            "content": "export const Button = () => <button>Click</button>;",
            "language": "typescript",
            "source_node_id": "node-001",
            "is_new": True,
        }
    ],
    "entry_point": "src/components/Button/Button.tsx",
    "component_exports": ["Button"],
})

@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    return FakeLLMAdapter(responses={"generate": _FAKE_NODE_RESPONSE})

@pytest.fixture
def generation_plan() -> GenerationPlan:
    return GenerationPlan(
        case_id="C-003",
        nodes=[
            GenerationNode(
                id="node-001",
                node_type="component",
                target_path="src/components/Button/Button.tsx",
            )
        ],
        execution_order=["node-001"],
    )

class TestCodeGenerator:
    @pytest.mark.asyncio
    async def test_generate_all_returns_artifact_set(
        self, fake_llm, generation_plan
    ) -> None:
        generator = CodeGenerator(llm=fake_llm)
        result = await generator.generate_all(
            plan=generation_plan,
            repo_profile=RepoProfile(framework="react"),
            intent_graph=IntentGraph(
                layout_regions=[], components=[], interactions=[],
                unresolved_items=[], confidence=0.9
            ),
            prompt="버튼 컴포넌트 생성",
        )
        assert isinstance(result, GeneratedArtifactSet)
        assert result.case_id == "C-003"
        assert len(result.files) == 1
        assert "src/components/Button/Button.tsx" in result.file_map

    @pytest.mark.asyncio
    async def test_generate_empty_plan_returns_empty_artifacts(
        self, fake_llm
    ) -> None:
        empty_plan = GenerationPlan(
            case_id="C-empty", nodes=[], execution_order=[]
        )
        generator = CodeGenerator(llm=fake_llm)
        result = await generator.generate_all(
            plan=empty_plan,
            repo_profile=RepoProfile(framework="react"),
            intent_graph=IntentGraph(
                layout_regions=[], components=[], interactions=[],
                unresolved_items=[], confidence=0.9
            ),
            prompt="",
        )
        assert len(result.files) == 0
        assert len(result.file_map) == 0
```

### OutputNormalizer 단위 테스트 패턴
```python
# tests/unit/services/test_output_normalizer.py
import json
import pytest
from ddk.services.output_normalizer import OutputNormalizer
from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.normalization import NormalizationReport
from ddk.models.repo import RepoProfile
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

_FAKE_NORMALIZATION_RESPONSE = json.dumps({
    "case_id": "C-003",
    "convention_fixes": [
        {
            "fix_type": "naming",
            "file_path": "src/components/button.tsx",
            "description": "Component file should use PascalCase",
            "before": "button.tsx",
            "after": "Button.tsx",
            "severity": "must-fix",
        }
    ],
    "unresolved_drift": [],
    "drift_score_before": 2.0,
    "drift_score_after": 0.0,
})

class TestOutputNormalizer:
    @pytest.mark.asyncio
    async def test_normalize_returns_report_and_patched_artifacts(
        self, ...
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={"normalize": _FAKE_NORMALIZATION_RESPONSE})
        normalizer = OutputNormalizer(llm=fake_llm)
        report, patched = await normalizer.normalize(
            artifacts=..., repo_profile=RepoProfile(framework="react")
        )
        assert isinstance(report, NormalizationReport)
        assert report.drift_score_before >= report.drift_score_after
        assert isinstance(patched, GeneratedArtifactSet)
```

### 7-node E2E 통합 테스트 패턴
```python
# tests/integration/test_generation_pipeline.py

_GENERATED_NODE_RESPONSE = json.dumps({
    "files": [
        {
            "path": "src/components/ProductCard/ProductCard.tsx",
            "content": "export const ProductCard = () => <div>Card</div>;",
            "language": "typescript",
            "source_node_id": "node-001",
            "is_new": True,
        }
    ],
    "entry_point": "src/components/ProductCard/ProductCard.tsx",
    "component_exports": ["ProductCard"],
})

_NORMALIZATION_RESPONSE = json.dumps({
    "case_id": "will-be-overwritten",
    "convention_fixes": [],
    "unresolved_drift": [],
    "drift_score_before": 0.0,
    "drift_score_after": 0.0,
})

pipeline_fake_llm = FakeLLMAdapter(responses={
    "you":        _INTENT_GRAPH_RESPONSE,      # SemanticIntentExtractor
    "analyze":    _DESIGN_SYSTEM_RESPONSE,     # DesignSystemInferencer
    "senior":     _GENERATION_PLAN_RESPONSE,   # GenerationPlanner
    "generate":   _GENERATED_NODE_RESPONSE,    # CodeGenerator ← NEW
    "normalize":  _NORMALIZATION_RESPONSE,     # OutputNormalizer ← NEW
})
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 자유 텍스트 LLM 응답 파싱 | `complete_structured()` tool_use 강제 | Phase 2 확립 | Phase 3에서도 동일 패턴 적용 |
| 단일 배치 코드 생성 | 노드별 개별 LLM 호출 | 설계 문서 §4 | 컨텍스트 집중, 병렬 처리 준비 가능 |
| Normalizer = AST 변환 | Normalizer = LLM(haiku) | 설계 문서 §6 | 외부 TS 파서 의존성 없음, 비용 최적화 |

---

## Open Questions

1. **`OutputNormalizer`의 파일 수정 범위**
   - What we know: `normalize()` → `(NormalizationReport, GeneratedArtifactSet)`; `NormalizationReport.convention_fixes`에 before/after 기록
   - What's unclear: normalizer가 파일 내용을 LLM이 직접 수정하는가, 아니면 수정 지침(ConventionFix)만 반환하고 서비스가 적용하는가?
   - Recommendation: 설계 문서 §6에 ConventionFix `before`/`after` snippet 기록이 명시됨. LLM이 수정된 파일 내용 전체를 반환하는 방식이 더 신뢰성 있음. 단, haiku의 4096 토큰 제한으로 큰 파일은 분리 호출 필요. Phase 3에서는 "LLM이 수정된 content 반환 + ConventionFix 기록" 방식 채택. 파일 크기 상한 500줄 제한 적용.

2. **GenerationNode 없는 빈 plan에서 generate_node 동작**
   - What we know: `FakeLLMAdapter`의 통합 테스트 fixture가 `execution_order: []` 반환
   - What's unclear: 빈 plan은 에러인가, 정상 케이스인가?
   - Recommendation: 빈 plan은 경고 로그만 남기고 `GeneratedArtifactSet(files=[], ...)` 반환. normalize도 빈 artifacts를 정상 처리.

3. **ServiceContainer에 CodeGenerator/OutputNormalizer 추가 여부**
   - What we know: Phase 2에서 service 필드를 `ServiceContainer`에 optional로 추가 (lines 52–57). Phase 3도 동일 패턴.
   - What's unclear: 노드 내부에서 `CodeGenerator(llm=container.llm)`으로 매번 생성 vs `container.code_generator`로 DI?
   - Recommendation: Phase 2 plan_node 패턴과 동일하게, 노드 내부에서 `CodeGenerator(llm=container.llm)` 직접 생성. ServiceContainer에 별도 서비스 필드 추가 불필요 (단순성 우선). 단, 향후 Phase 4에서 auto-fix가 CodeGenerator를 재사용한다면 ServiceContainer 필드 추가가 필요할 수 있음 → Phase 4에서 결정.

---

## Environment Availability

Step 2.6: SKIPPED (Phase 3은 기존 인프라 위에 서비스/노드 코드 추가. 새로운 외부 의존성 없음. Python, uv, anthropic SDK 모두 Phase 2에서 검증됨.)

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (Phase 1/2에서 확립) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/unit/services/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CODEGEN-01 | `generate_all()` returns `GeneratedArtifactSet` with files | unit | `uv run pytest tests/unit/services/test_code_generator.py -x` | ❌ Wave 0 |
| CODEGEN-01 | Empty plan returns empty artifact set | unit | `uv run pytest tests/unit/services/test_code_generator.py::test_generate_empty_plan -x` | ❌ Wave 0 |
| CODEGEN-01 | `generate_node` thin adapter wires correctly | unit | `uv run pytest tests/unit/nodes/test_generate_node.py -x` | ❌ Wave 0 |
| CODEGEN-02 | `normalize()` returns `NormalizationReport` + patched artifacts | unit | `uv run pytest tests/unit/services/test_output_normalizer.py -x` | ❌ Wave 0 |
| CODEGEN-02 | `drift_score_before >= drift_score_after` | unit | same | ❌ Wave 0 |
| CODEGEN-02 | `normalize_node` thin adapter wires correctly | unit | `uv run pytest tests/unit/nodes/test_normalize_node.py -x` | ❌ Wave 0 |
| SC-3 | 7-node pipeline E2E with FakeLLM | integration | `uv run pytest tests/integration/test_generation_pipeline.py -x` | ❌ Wave 0 |
| SC-3 | Model reconciliation: `NormalizationReport.drift_score_before` field | unit | `uv run pytest tests/unit/models/test_output_models.py -x` | ✅ exists (requires model update) |
| SC-3 | Existing 286 tests still pass after model changes | regression | `uv run pytest tests/ -q` | ✅ exists |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/services/ tests/unit/models/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q` (286+ tests green)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/services/test_code_generator.py` — covers CODEGEN-01 unit tests
- [ ] `tests/unit/services/test_output_normalizer.py` — covers CODEGEN-02 unit tests
- [ ] `tests/integration/test_generation_pipeline.py` — 7-node E2E (확장 or 신규)
- [ ] `tests/unit/nodes/test_generate_node.py` — thin adapter test (optional, covered by integration)
- [ ] `tests/unit/nodes/test_normalize_node.py` — thin adapter test (optional)

---

## Recommended Wave Structure

```
Wave 0: 모델 정렬 (필수 선행)
  - GeneratedArtifactSet/GeneratedFile 필드 추가 (is_new, original_content, schema_version)
  - NormalizationReport/ConventionFix 필드 추가 (fix_type, severity, drift_score_*,
    convention_fixes → 별칭 or 교체, before/after → 별칭)
  - compute_drift_score() 정적 메서드 추가
  - 기존 286 테스트 통과 유지
  - 신규 모델 단위 테스트 작성

Wave 1: CodeGenerator 서비스 + generate_node
  - src/ddk/services/code_generator.py
    - _GeneratedNodeOutput 내부 모델
    - _SYSTEM_PROMPT ("Generate" 시작)
    - CodeGenerator.generate_all() 구현
  - src/ddk/graph/nodes/generate.py (thin adapter)
  - tests/unit/services/test_code_generator.py

Wave 2: OutputNormalizer 서비스 + normalize_node
  - src/ddk/services/output_normalizer.py
    - _SYSTEM_PROMPT ("Normalize" 시작)
    - OutputNormalizer.normalize() 구현
    - drift_score 계산 포함
  - src/ddk/graph/nodes/normalize.py (thin adapter)
  - tests/unit/services/test_output_normalizer.py
  (순차: Wave 1 GeneratedArtifactSet 구조 확정 후 착수)

Wave 3: 7-node 그래프 조립 + E2E
  - builder.py: plan → generate → normalize → END
  - FakeLLMAdapter 응답 키 확장 ("generate", "normalize")
  - tests/integration/test_generation_pipeline.py: 7-node E2E
  - 성공 기준: 6-node sub-graph E2E가 FakeLLM으로 통과
```

**병렬성:** Wave 0 완료 → Wave 1과 Wave 2는 순차 진행 (Wave 2가 Wave 1 출력 모델에 의존). Wave 1/2 완료 → Wave 3.

---

## Project Constraints (from copilot-instructions.md)

*`copilot-instructions.md` 파일 미발견. PROJECT.md와 ADR에서 추출한 하드 제약:*

| Constraint | Source | Impact on Phase 3 |
|------------|--------|-------------------|
| Python 3.12+ | PROJECT.md | `StrEnum`, `datetime.UTC` 사용 (Phase 1 확립) |
| uv 패키지 매니저 | ADR-015 | `uv run pytest` 사용 |
| Pydantic v2 | PROJECT.md | `model_validate()`, `model_dump_json()` 패턴 |
| Ruff + Pyright strict | PROJECT.md | `from __future__ import annotations`, 타입 힌트 완전 명시 |
| LangGraph StateGraph | ADR-010 | context_schema DI, node_wrapper 패턴 |
| temperature=0 | 16-prompt-design.md | CodeGenerator, OutputNormalizer 모두 적용 |
| cost ≤ $0.10/case | PROJECT.md | CodeGenerator=sonnet, OutputNormalizer=haiku |

---

## Sources

### Primary (HIGH confidence)
- `docs/design/16-prompt-design.md` — §4 CodeGenerator 프롬프트 전체, §6 ConventionNormalizer 프롬프트 전체
- `docs/design/12-data-models.md` — GeneratedArtifactSet, NormalizationReport 설계 명세
- `docs/design/04-system-design.md` — generate_node/normalize_node 노드 계약, 서비스 레이어 구조
- `docs/design/19-langgraph-builder.md` — 전체 10-node 그래프 흐름, generate/normalize 노드 시그니처
- `src/ddk/models/generation.py` — 기존 구현 모델 (Phase 1)
- `src/ddk/models/normalization.py` — 기존 구현 모델 (Phase 1)
- `src/ddk/graph/builder.py` — 현재 5-node partial graph (Phase 2 D-08)
- `src/ddk/services/generation_planner.py` — Phase 2 서비스 패턴 준용
- `tests/integration/test_ingestion_pipeline.py` — FakeLLM 키 전략 및 E2E 테스트 구조

### Secondary (MEDIUM confidence)
- `.planning/phases/02-ingestion-analysis/02-CONTEXT.md` — D-05~D-08 locked decisions
- `.planning/phases/02-ingestion-analysis/VERIFICATION.md` — Phase 2 구현 확인 (286 tests pass)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Phase 1/2에서 확립된 스택 그대로 사용
- Architecture: HIGH — 설계 문서(16, 12, 04, 19)가 CodeGenerator/OutputNormalizer 구조를 완전히 명시
- Pitfalls: HIGH — 코드베이스에서 직접 발견된 FakeLLM 키 충돌, 모델 필드 불일치
- Model gaps: HIGH — `src/ddk/models/` 실제 코드와 `docs/design/12-data-models.md` 직접 비교

**Research date:** 2025-07-28
**Valid until:** 2026-04-28 (stable domain; 모델 설계 문서 변경 시 재검토)

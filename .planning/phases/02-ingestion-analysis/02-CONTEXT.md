# Phase 2: Ingestion & Analysis - Context

**Gathered:** 2025-07-28
**Status:** Ready for planning

<domain>
## Phase Boundary

디자인 시안(이미지+프롬프트)을 받아 5단계 분석 파이프라인(intake → repo_scan → intent_extract → design_system → plan)을 구현한다. Phase 1 기반(40+ Pydantic 모델, FakeLLMAdapter, ServiceContainer)을 재사용하며, 첫 실제 LLM 호출 Phase로 비용 추적과 구조화 출력 파싱 패턴을 확립한다.

**Requirements:** INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, CODEGEN-03

**Services to implement (5개):**
1. `IntakeProcessor` — CaseInput 검증 및 이미지 메타데이터 추출
2. `RepoConventionScanner` — 정적 분석 + LLM(haiku) 보완으로 RepoProfile 생성
3. `SemanticIntentExtractor` — LLM(sonnet) 구조화 출력으로 IntentGraph 생성
4. `DesignSystemInferencer` — LLM(sonnet) 구조화 출력으로 DesignSystem 추론
5. `GenerationPlanner` — 결정론적 알고리즘으로 GenerationPlan 생성
6. `ContextPackBuilder` — 결정론적 우선순위 알고리즘으로 컨텍스트 패키징

**Partial Graph to assemble in Phase 2:**
```
START → intake → repo_scan → intent_extract → design_system → plan → END
```

</domain>

<decisions>
## Implementation Decisions

### 서비스 레이어 분리 방식
- **D-05:** `src/ddk/services/` 레이어를 생성한다. 각 서비스 클래스(비즈니스 로직)는 서비스 파일에, LangGraph 노드는 `src/ddk/graph/nodes/`에 Thin Adapter로 분리한다. 노드는 상태 읽기·서비스 호출·상태 쓰기만 담당하며 로직이 없다.
  - `src/ddk/services/intake_processor.py`
  - `src/ddk/services/repo_convention_scanner.py`
  - `src/ddk/services/semantic_intent_extractor.py`
  - `src/ddk/services/design_system_inferencer.py`
  - `src/ddk/services/generation_planner.py`
  - `src/ddk/services/context_pack_builder.py`
  - 노드: `src/ddk/graph/nodes/intake.py`, `repo_scan.py`, `intent_extract.py`, `design_system.py`, `plan.py`

### LLM 테스트 전략
- **D-06:** 모든 서비스 단위 테스트는 `FakeLLMAdapter`를 사용한다. `@pytest.mark.integration` 마커로 실제 `ANTHROPIC_API_KEY` 사용하는 통합 테스트를 선택적으로 추가한다. `ServiceContainer`에 `ClaudeAdapter` 연결 코드는 Phase 2에 포함한다.
  - 단위: `FakeLLMAdapter` (API 키 불필요, CI/CD 항상 실행)
  - 통합: `@pytest.mark.integration` (실제 API 호출, 로컬/CI 선택적)
  - `conftest.py`에 `ANTHROPIC_API_KEY` 없으면 통합 테스트 자동 skip

### RepoConventionScanner 구현 전략
- **D-07:** 정적 분석 주 + LLM(haiku) 보완 방식을 채택한다.
  - **1단계 정적 파싱** (파일 존재 시):
    - `package.json` → 프레임워크(React/Vue/Angular), 의존성 버전
    - `tsconfig.json` → TypeScript 설정(strict, paths, target)
    - `.eslintrc.*` / `.prettierrc.*` → 코드 스타일(세미콜론, 인용, 들여쓰기)
    - `pyproject.toml` → Python 스택(FastAPI/Django, 테스팅, 린터)
  - **2단계 LLM 보완** (정적 파싱 미확인 패턴):
    - 파일 트리 샘플(최대 50개 경로)을 haiku에게 전달
    - 네이밍 컨벤션(PascalCase/camelCase), 컴포넌트 구조, 디자인 시스템 패턴 추론
    - LLM 호출은 정적 분석 결과가 불충분할 때만 실행

### Phase 2 builder.py 연결 범위
- **D-08:** Phase 2 완료 시 5개 노드를 `builder.py`에 연결하여 실행 가능한 Partial Graph를 만든다.
  - 기존 `_start_node` 플레이스홀더를 실제 `intake` 노드로 교체
  - 엣지: `START → intake → repo_scan → intent_extract → design_system → plan → END`
  - Phase 3에서 `generate`, `normalize` 노드를 이어 붙임
  - 이점: Phase 2 integration test에서 실제 파이프라인 실행 가능

### 에이전트 재량 영역
- 서비스 클래스 내부 헬퍼 메서드 분리는 에이전트 자율 결정
- `conftest.py` fixture 재사용 패턴은 에이전트가 Phase 1 패턴을 따름
- 정적 파싱 실패(파일 없음) 처리 방식은 `RepoProfile.framework = "unknown"`으로 기본값 설정

</decisions>

<specifics>
## Specific Ideas

- **Thin Node 패턴** (D-05 실현):
  ```python
  # nodes/repo_scan.py — 노드: 상태 입출력만
  async def repo_scan_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
      container: ServiceContainer = kwargs["container"]
      scanner = container.repo_convention_scanner
      profile = await scanner.scan(Path(state["workspace_path"]))
      return {"repo_profile": profile, "current_node": "repo_scan"}

  # services/repo_convention_scanner.py — 서비스: 로직 전담
  class RepoConventionScanner:
      async def scan(self, repo_path: Path) -> RepoProfile: ...
  ```

- **`@pytest.mark.integration` 패턴** (D-06 실현):
  ```python
  # conftest.py
  def pytest_configure(config):
      config.addinivalue_line("markers", "integration: real API calls")

  # tests/integration/test_intent_extractor.py
  @pytest.mark.integration
  async def test_extract_intent_real_api(real_claude_adapter):
      ...
  ```

- **ContextPackBuilder 결정론적 정렬** (`24-context-pack-determinism.md` 구현):
  ```python
  sort_key = (priority_rank, relation_rank, line_bucket, normalized_path)
  # MAX_FILES=6, MAX_LINES=300, 사전순 tie-break
  ```

- **LLM 구조화 출력** (`ClaudeAdapter.complete_structured()` 재사용):
  ```python
  # IntentGraph 파싱
  result = await adapter.complete_structured(
      prompt=..., response_schema=IntentGraph.model_json_schema(), config=config
  )
  intent_graph = IntentGraph.model_validate(result)
  ```

- **Partial Graph 연결** (D-08):
  ```python
  # builder.py — Phase 2 이후
  workflow.add_node("intake", node_wrapper(intake_node))
  workflow.add_node("repo_scan", node_wrapper(repo_scan_node))
  workflow.add_node("intent_extract", node_wrapper(intent_extract_node))
  workflow.add_node("design_system", node_wrapper(design_system_node))
  workflow.add_node("plan", node_wrapper(plan_node))
  workflow.add_edge(START, "intake")
  workflow.add_edge("intake", "repo_scan")
  workflow.add_edge("repo_scan", "intent_extract")
  workflow.add_edge("intent_extract", "design_system")
  workflow.add_edge("design_system", "plan")
  workflow.add_edge("plan", END)
  ```

</specifics>

<canonical_refs>
## Canonical References

**다운스트림 에이전트는 계획 또는 구현 전에 반드시 아래 문서를 읽어야 한다.**

### LLM 인터페이스 & 라우팅
- `docs/design/11-llm-interface.md` — LLM 라우팅 정책(intent_extract=sonnet, repo_scan=haiku), `safe_llm_call` 규칙, 환경변수 정의, 비용 버짓
- `docs/design/16-prompt-design.md` — SemanticIntentExtractor 시스템 프롬프트 전체, IntentGraph JSON 스키마 출력 포맷

### Context Pack
- `docs/design/24-context-pack-determinism.md` — ContextPackBuilder 결정론적 알고리즘 전체 명세 (P1~P5 우선순위, sort_key, MAX_FILES=6, MAX_LINES=300)

### 서비스 레이어 & 파이프라인
- `docs/design/04-system-design.md` §서비스 레이어 — `src/ddk/services/context_pack_builder.py` 구현 계약, 파이프라인 흐름(intake→repo_scan→intent_extract→plan)
- `docs/design/04-system-design.md` §5 State Machine 흐름 — 전체 10-노드 파이프라인 확인 (Phase 2는 앞 5개)

### 데이터 모델 (재사용)
- `docs/design/12-data-models.md` — CaseInput, RepoProfile, IntentGraph, DesignSystem, GenerationPlan, ContextPack 모델 (Phase 1에서 이미 구현됨)
- `src/ddk/models/` — Phase 1에서 구현된 40+ Pydantic 모델 직접 참조

### 어댑터 & DI (Phase 1 기반 재사용)
- `src/ddk/adapters/llm/claude.py` — `ClaudeAdapter`: `complete()` + `complete_structured()` (tool_use 방식) 완전 구현 (139줄)
- `src/ddk/adapters/llm/fake.py` — `FakeLLMAdapter`: 단위 테스트에서 사용
- `src/ddk/graph/context.py` — `ServiceContainer` @dataclass DI 컨테이너
- `src/ddk/graph/nodes/_wrapper.py` — `node_wrapper()`: OS/timeout 에러 바운더리, `**kwargs` 패턴

### 노드 패턴
- `docs/design/04-system-design.md` §_node_wrapper — `async def fn(state: dict, **kwargs) -> dict` 패턴 확정
- `src/ddk/graph/builder.py` — 기존 `build_ddk_graph()` 구조 (Phase 2에서 5노드 추가)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (Phase 1에서 이미 완성)
- `src/ddk/models/` — 40+ Pydantic v2 모델: `CaseInput`, `RepoProfile`, `IntentGraph`, `DesignSystem`, `GenerationPlan`, `ContextPack` 등 Phase 2에서 그대로 사용
- `src/ddk/adapters/llm/claude.py` — `ClaudeAdapter` 완전 구현: `complete(prompt, config)` + `complete_structured(prompt, schema, config)` (tool_use 강제)
- `src/ddk/adapters/llm/fake.py` — `FakeLLMAdapter`: 구조화 출력(JSON schema) 시뮬레이션 지원 — 단위 테스트 핵심
- `src/ddk/graph/context.py` — `ServiceContainer` @dataclass: 모든 어댑터 Protocol 인스턴스 보유
- `src/ddk/graph/state.py` — `GraphState` TypedDict (21 필드): `case_input`, `repo_profile`, `intent_graph` 등 이미 정의됨
- `src/ddk/graph/nodes/_wrapper.py` — `node_wrapper()`: 모든 Phase 2 노드가 이 패턴을 따름
- `src/ddk/graph/builder.py` — `build_ddk_graph()`: Phase 2에서 5노드 추가 예정 (현재 START→start→END 플레이스홀더)
- `tests/fakes/` — 8개 테스트 더블: `FakeLLMAdapter`, `InMemoryFilesystem` 등

### Patterns to Follow
- `node_wrapper(fn)` 래핑: 모든 노드 함수를 `node_wrapper`로 감싸서 에러 바운더리 적용
- `async def fn(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]` 노드 시그니처
- `FakeLLMAdapter`의 `set_response()` 메서드로 테스트별 LLM 응답 제어
- Pydantic `model_validate()` + `model_dump()` roundtrip 패턴
- structlog `bind()` 기반 per-node 컨텍스트 로깅

### Patterns to Avoid
- 노드 함수에 비즈니스 로직 직접 작성 (D-05: 서비스 레이어로 분리)
- `state["list"].append()` (LangGraph 상태 뮤테이션 오염 — 불변 패턴 필수)
- LLM을 정적 분석으로 충분할 때 호출 (D-07: 정적 분석 주, LLM은 보완)
- 통합 테스트에 `@pytest.mark.integration` 마커 누락

### ServiceContainer 연결 (Phase 2에 추가)
Phase 2에서 `ServiceContainer`에 `ClaudeAdapter` 인스턴스를 연결하는 팩토리 함수를 추가한다:
```python
# src/ddk/graph/context.py 또는 별도 factory.py
def create_production_container() -> ServiceContainer:
    return ServiceContainer(
        llm_adapter=ClaudeAdapter.from_env(),
        ...
    )
```

</code_context>

<deferred>
## Deferred Ideas

- Multi-provider LLM fallback (OpenAI/Gemini) — Phase 5 이후 / Milestone v2.0
- 이미지 전처리 파이프라인 (resize, crop, format) — Phase 3 이후 검토
- Repo scanner 캐싱 (git hash 기반) — Phase 3에서 성능 최적화 시 고려
- Streaming LLM 응답 — Phase 5 이후 UX 개선
- context pack hash 기반 재사용 — Phase 5 EvidencePack 구현 시 검토

</deferred>

---

*Phase: 02-ingestion-analysis*
*Context gathered: 2025-07-28*

# Phase 02: Ingestion & Analysis — Research

**Researched:** 2025-07-28
**Domain:** LangGraph services layer, LLM-structured output, static file analysis, context pack determinism
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-05:** `src/ddk/services/` 레이어를 생성한다. 각 서비스 클래스(비즈니스 로직)는 서비스 파일에, LangGraph 노드는 `src/ddk/graph/nodes/`에 Thin Adapter로 분리한다. 노드는 상태 읽기·서비스 호출·상태 쓰기만 담당하며 로직이 없다.
- **D-06:** 모든 서비스 단위 테스트는 `FakeLLMAdapter`를 사용한다. `@pytest.mark.integration` 마커로 실제 `ANTHROPIC_API_KEY` 사용하는 통합 테스트를 선택적으로 추가한다. `ServiceContainer`에 `ClaudeAdapter` 연결 코드는 Phase 2에 포함한다.
- **D-07:** 정적 분석 주 + LLM(haiku) 보완 방식을 채택한다. 1단계: `package.json`, `tsconfig.json`, `.eslintrc.*`, `.prettierrc.*`, `pyproject.toml` 정적 파싱. 2단계: 정적 파싱 미확인 패턴에 대해 파일 트리 샘플(최대 50개 경로)을 haiku에게 전달.
- **D-08:** Phase 2 완료 시 5개 노드를 `builder.py`에 연결하여 실행 가능한 Partial Graph를 만든다. `START → intake → repo_scan → intent_extract → design_system → plan → END`

### the agent's Discretion

- 서비스 클래스 내부 헬퍼 메서드 분리는 에이전트 자율 결정
- `conftest.py` fixture 재사용 패턴은 에이전트가 Phase 1 패턴을 따름
- 정적 파싱 실패(파일 없음) 처리 방식은 `RepoProfile.framework = "unknown"`으로 기본값 설정

### Deferred Ideas (OUT OF SCOPE)

- Multi-provider LLM fallback (OpenAI/Gemini) — Phase 5 이후 / Milestone v2.0
- 이미지 전처리 파이프라인 (resize, crop, format) — Phase 3 이후 검토
- Repo scanner 캐싱 (git hash 기반) — Phase 3에서 성능 최적화 시 고려
- Streaming LLM 응답 — Phase 5 이후 UX 개선
- context pack hash 기반 재사용 — Phase 5 EvidencePack 구현 시 검토
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INGEST-02 | Multimodal Intake — 이미지/프롬프트/레퍼런스 텍스트를 CaseInput으로 검증·구조화 | `CaseInput` 모델 완전 구현됨; `IntakeProcessor` 서비스가 이미지 경로 존재 검증 + 이미지 해시 계산 담당 |
| INGEST-03 | Repo Convention Scan — RepoConventionScanner 서비스, 프레임워크/네이밍/스타일/파일 레이아웃 → `RepoProfile` | D-07 정적+LLM 하이브리드; `package.json`, `tsconfig.json`, `.eslintrc`, `.prettierrc` 파싱 패턴 확정 |
| INGEST-04 | Semantic Intent Model — SemanticIntentExtractor, 레이아웃/인터랙션/콘텐츠 인텐트 → `IntentGraph` | `claude-3-5-sonnet` + tool_use; `16-prompt-design.md §1` 프롬프트 전체 정의됨; **이미지 전송 위한 Message 확장 필요** |
| INGEST-05 | Design System Inference — DesignSystemInferencer, 토큰/스페이싱/타이포그래피 추론 | `DesignSystem` 모델 미존재 → Phase 2에서 신규 생성 필요; 추론 결과를 `repo_profile` 또는 별도 상태로 저장하는 설계 결정 필요 |
| INGEST-06 | Generation Plan Graph — GenerationPlanner, ordered graph → `GenerationPlan` | `16-prompt-design.md §3` 프롬프트 정의됨; **구현된 `GenerationPlan` 스키마가 설계 문서와 다름** (하단 Critical Gap 참조) |
| CODEGEN-03 | Context Pack Builder — ContextPackBuilder, MAX_FILES=6/MAX_LINES=300, P1~P5, 사전순 tie-break | `24-context-pack-determinism.md` 전체 알고리즘 명세 완비; sort_key = (priority_rank, relation_rank, line_bucket, normalized_path) |
</phase_requirements>

---

## Summary

Phase 2는 딸깍 파이프라인의 첫 번째 실제 LLM 호출 Phase다. Phase 1이 구축한 40+ Pydantic 모델, `ClaudeAdapter`, `FakeLLMAdapter`, `ServiceContainer`, `node_wrapper`를 모두 재사용하며, 6개 서비스 클래스와 5개 노드를 신규 작성한다.

**가장 중요한 사전 조사 결과:** (1) `DesignSystem` 과 `ContextPack` Pydantic 모델이 `src/ddk/models/`에 아직 없다 — Phase 2에서 신규 생성 필요. (2) `Message` 데이터클래스가 이미지(base64) 첨부를 지원하지 않는다 — `SemanticIntentExtractor`가 이미지를 Claude에 보내려면 `Message`를 확장하거나 별도 이미지 전송 로직이 필요하다. (3) 구현된 `GenerationNode`/`GenerationPlan` 스키마가 `12-data-models.md` 설계 문서와 필드명이 다르다 — 플래너는 어느 스키마를 기준으로 서비스를 구현할지 결정해야 한다.

**Primary recommendation:** 각 서비스를 독립적으로 구현하고 `FakeLLMAdapter`로 단위 테스트를 먼저 작성한 뒤, 5개 노드를 `builder.py`에 연결하여 부분 그래프 통합 테스트로 마무리한다. LLM 호출 서비스 2개(intent_extract, design_system)와 결정론적 서비스 4개(intake, repo_scan, generation_planner, context_pack_builder)를 명확히 분리하여 계획하라.

---

## Standard Stack

### Core (Phase 1에서 이미 설치됨)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `anthropic` | ≥0.40.0 | Claude API (tool_use 구조화 출력) | `ClaudeAdapter`가 이미 구현됨 |
| `langgraph` | ≥1.0.0 | 5-노드 StateGraph 조립 | Phase 1 DI 패턴 확립됨 |
| `pydantic` | ≥2.7.0 | 모델 검증 + `model_json_schema()` | 40+ 모델 이미 구현됨 |
| `structlog` | ≥24.0.0 | per-node 컨텍스트 로깅 | Phase 1 패턴 확립됨 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` (stdlib) | — | package.json, tsconfig.json 정적 파싱 | RepoConventionScanner 1단계 |
| `pathlib.Path` (stdlib) | — | 파일 트리 탐색, 50개 경로 샘플링 | RepoConventionScanner |
| `hashlib` (stdlib) | — | 이미지 SHA256[:16] 계산 | IntakeProcessor, ContextPackBuilder |
| `base64` (stdlib) | — | 이미지 base64 인코딩 | SemanticIntentExtractor |
| `math.ceil` (stdlib) | — | `line_bucket = ceil(lines / 50)` | ContextPackBuilder sort_key |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 정적 파싱 우선 | LLM-only repo scan | LLM이 비용 더 비쌈; 정적이 충분할 때 낭비 (D-07 결정) |
| `tool_use` 구조화 출력 | `response_format` JSON | Anthropic은 `tool_use`가 더 안정적; OpenAI는 `beta.chat.completions.parse()` — Phase 2는 Anthropic only |

**Version verification:** 모든 의존성은 Phase 1 `pyproject.toml`에 이미 설치됨. 추가 패키지 불필요.

---

## Critical Gaps (반드시 계획에 포함)

### Gap 1: `Message` 이미지 지원 부재 ⚠️ HIGH RISK

**현황:** `src/ddk/adapters/llm/base.py`의 `Message` 데이터클래스는 `role: str`과 `content: str`만 있다. 이미지 첨부 필드가 없다.

**영향:** `SemanticIntentExtractor`는 Claude에 이미지(base64)를 보내야 한다 (`16-prompt-design.md §1` 참조). 현재 `ClaudeAdapter.complete_structured()`는 이미지 없이 텍스트만 전달한다.

**해결 옵션:**
```python
# Option A: Message에 optional images 추가
@dataclass
class Message:
    role: str
    content: str
    images: list[tuple[str, str]] | None = None  # [(base64_data, media_type), ...]

# Option B: 이미지 전용 별도 메서드
async def complete_structured_with_image(
    self,
    messages: list[Message],
    images: list[tuple[str, str]],  # [(base64_data, media_type), ...]
    config: LLMCallConfig,
    output_schema: type,
) -> LLMResponse: ...
```

**권장:** Option A — `Message`에 `images: list[tuple[str, str]] | None = None` 추가. 하위 호환 (기존 테스트 무파괴). `ClaudeAdapter._split_messages()`에서 이미지 블록을 Anthropic API content 형식으로 변환.

**`FakeLLMAdapter` 처리:** `complete_structured()`가 이미지를 무시하고 canned 응답을 반환하므로 단위 테스트는 변경 불필요.

---

### Gap 2: `DesignSystem` 모델 미존재 ⚠️ MEDIUM RISK

**현황:** `src/ddk/models/`에 `DesignSystem` 모델이 없다. `GraphState`에도 해당 필드가 없다.

**설계 문서 근거:** `04-system-design.md §Level 3`에 `DesignSystemInferencer`가 명시됨. `CONTEXT.md`에서 서비스 출력이 "DesignSystem"으로 기술됨.

**권장 해결:** `DesignSystem` 모델은 신규 생성하되, 그 출력은 **`repo_profile`을 업데이트하는 방식**으로 GraphState 변경 없이 처리한다:
```python
# src/ddk/models/design_system.py
class InferredDesignToken(DDKBaseModel):
    name: str
    value: str
    category: Literal["color", "spacing", "typography", "border_radius", "breakpoint"]
    confidence: float = Field(ge=0.0, le=1.0)

class DesignSystem(DDKBaseModel):
    case_id: str
    inferred_tokens: list[InferredDesignToken]
    primitive_components: list[str]   # 재사용 가능 컴포넌트 이름
    token_source: Literal["static", "llm", "hybrid"] = "hybrid"
    schema_version: str = "1.0"
```

`design_system` 노드: `DesignSystemInferencer.infer()` → `DesignSystem` → `repo_profile.design_tokens`를 풍부화하여 반환:
```python
async def design_system_node(state, **kwargs):
    ...
    enriched_profile = inferencer.enrich_profile(design_system, state["repo_profile"])
    return {"repo_profile": enriched_profile, "current_node": "design_system"}
```

GraphState에 `design_system` 필드를 추가하려면 기존 207개 테스트에서 GraphState dict를 생성하는 코드를 모두 업데이트해야 하므로 **GraphState 변경은 피할 것을 권장**한다.

---

### Gap 3: `ContextPack` 모델 미존재 ⚠️ MEDIUM RISK

**현황:** `src/ddk/models/`에 `ContextPack` 모델이 없다. `GraphState`에도 해당 필드가 없다.

**설계 문서 근거:** `24-context-pack-determinism.md §6.1`에 `ContextPackManifest` JSON 구조가 정의됨. `04-system-design.md §7`에 `ContextPackBuilder` 구현 계약이 있다.

**권장 해결:**
```python
# src/ddk/models/context_pack.py
class ContextChunk(DDKBaseModel):
    path: str
    priority: Literal["P1", "P2", "P3", "P4", "P5"]
    start_line: int
    end_line: int
    content: str
    content_sha256: str

class ContextPack(DDKBaseModel):
    node_name: str
    target_files: list[str]
    chunks: list[ContextChunk]
    total_lines: int
    insufficient_context: bool = False
    missing_context_for: list[str] = Field(default_factory=list)
    context_pack_hash: str  # SHA256[:16] of canonical manifest JSON
    schema_version: str = "1.0"
```

`ContextPackBuilder`는 Phase 2에서 구현하고 테스트하되, **실제 호출은 Phase 3 `generate` 노드에서 수행**된다. Phase 2 `plan` 노드에서 ContextPackBuilder를 미리 실행하여 `insufficient_context` 여부를 검증하고, 해당 결과를 `generation_plan`의 메타데이터 또는 별도 검증 결과로 저장한다.

---

### Gap 4: `GenerationPlan` 스키마 불일치 ⚠️ LOW RISK (확인 후 결정)

**현황:**
- 구현된 `GenerationNode` (Phase 1): `id`, `task_description`, `dependencies`, `output_files`, `validation_hook`, `repair_hook`, `priority`
- 설계 문서 `GenerationNode` (12-data-models.md): `id`, `node_type`, `target_path`, `dependencies`, `validation_hooks`, `repair_hooks`, `generation_prompt_hint`

**중요 차이:**
- 설계 문서에는 `node_type: Literal["file", "component", "hook", "style", "test", "route", "type"]`와 `target_path: str`이 있어 Phase 3 코드 생성기가 어떤 파일을 어디에 생성할지 알 수 있다.
- 구현에는 `task_description`과 `output_files`만 있다.

**권장:** `16-prompt-design.md §3`의 GenerationPlanner 프롬프트는 `execution_order`가 있는 설계 문서 버전을 사용한다. Phase 2 `GenerationPlanner` 서비스는 **설계 문서의 필드명을 따르도록 `generation.py` 모델을 업데이트**해야 한다. 단, 기존 모델 테스트가 파괴되므로 업데이트 테스트도 함께 수정해야 한다.

---

### Gap 5: `@pytest.mark.integration` 미설정

**현황:** `pyproject.toml`에 `markers` 설정이 없다. `tests/conftest.py`에 integration skip guard도 없다.

**필요 추가:**
```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "integration: real API calls — requires ANTHROPIC_API_KEY",
]
```
```python
# tests/conftest.py
import pytest
import os

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: real API calls — requires ANTHROPIC_API_KEY"
    )

@pytest.fixture(scope="session")
def anthropic_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")
    return key
```

---

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
src/ddk/
├── services/                    # NEW — Phase 2 서비스 레이어
│   ├── __init__.py
│   ├── intake_processor.py      # INGEST-02
│   ├── repo_convention_scanner.py  # INGEST-03
│   ├── semantic_intent_extractor.py  # INGEST-04
│   ├── design_system_inferencer.py   # INGEST-05
│   ├── generation_planner.py    # INGEST-06
│   └── context_pack_builder.py  # CODEGEN-03
├── models/
│   ├── design_system.py         # NEW — DesignSystem, InferredDesignToken
│   └── context_pack.py          # NEW — ContextPack, ContextChunk
├── graph/
│   └── nodes/
│       ├── intake.py            # NEW — Thin Adapter
│       ├── repo_scan.py         # NEW — Thin Adapter
│       ├── intent_extract.py    # NEW — Thin Adapter
│       ├── design_system.py     # NEW — Thin Adapter
│       └── plan.py              # NEW — Thin Adapter
└── adapters/
    └── llm/
        └── base.py              # MODIFY — Message에 images 필드 추가
tests/
├── unit/
│   ├── services/                # NEW
│   │   ├── test_intake_processor.py
│   │   ├── test_repo_convention_scanner.py
│   │   ├── test_semantic_intent_extractor.py
│   │   ├── test_design_system_inferencer.py
│   │   ├── test_generation_planner.py
│   │   └── test_context_pack_builder.py
│   └── nodes/                   # NEW
│       └── test_nodes_thin_adapter.py
└── integration/
    └── test_ingestion_pipeline.py  # NEW — 5-노드 그래프 E2E
```

### Pattern 1: Thin Node Pattern (D-05)

**What:** 노드 함수는 상태 읽기 → 서비스 호출 → 상태 쓰기만. 로직 없음.
**When to use:** 모든 Phase 2 노드.

```python
# src/ddk/graph/nodes/repo_scan.py
from __future__ import annotations
from typing import Any
from pathlib import Path
from ddk.graph.context import ServiceContainer

async def repo_scan_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    container: ServiceContainer = kwargs["container"]
    scanner = container.repo_convention_scanner  # ServiceContainer에 추가 예정
    profile = await scanner.scan(Path(state["case_input"].repo_path))
    return {"repo_profile": profile, "current_node": "repo_scan"}
```

### Pattern 2: LLM-backed Service with FakeLLMAdapter Testing

**What:** LLM 의존 서비스는 Protocol을 통해 adapter를 주입받아 `FakeLLMAdapter`로 단위 테스트.

```python
# src/ddk/services/semantic_intent_extractor.py
class SemanticIntentExtractor:
    def __init__(self, llm: LLMAdapter) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.0,
            max_tokens=4096,
        )

    async def extract(
        self,
        case_input: CaseInput,
    ) -> IntentGraph:
        # 이미지 base64 인코딩
        image_path = case_input.image_paths[0]
        image_b64 = base64.standard_b64encode(image_path.read_bytes()).decode()
        image_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()[:16]

        messages = [
            Message(role="system", content=INTENT_EXTRACT_SYSTEM_PROMPT),
            Message(
                role="user",
                content=f"...",
                images=[(image_b64, "image/png")],  # Message 확장 후
            ),
        ]
        response = await self._llm.complete_structured(
            messages, self._config, output_schema=IntentGraph
        )
        data = json.loads(response.content)
        data["source_image_hash"] = image_hash
        return IntentGraph.model_validate(data)
```

### Pattern 3: Static-first Repo Scanning (D-07)

**What:** 파일 존재 여부를 먼저 검사하고, 정적 파싱으로 충분하면 LLM 호출 없이 반환.

```python
# src/ddk/services/repo_convention_scanner.py
class RepoConventionScanner:
    async def scan(self, repo_path: Path) -> RepoProfile:
        # 1단계: 정적 파싱
        profile = self._static_scan(repo_path)

        # 2단계: 정적이 불충분할 때만 LLM 보완
        if self._needs_llm_supplement(profile):
            profile = await self._llm_supplement(profile, repo_path)

        return profile

    def _static_scan(self, repo_path: Path) -> RepoProfile:
        pkg = self._parse_package_json(repo_path / "package.json")
        ts = self._parse_tsconfig(repo_path / "tsconfig.json")
        eslint = self._parse_eslint(repo_path)
        return self._build_profile(pkg, ts, eslint)

    def _needs_llm_supplement(self, profile: RepoProfile) -> bool:
        return profile.framework == "other" or not profile.naming_rules.component_pattern
```

### Pattern 4: ContextPackBuilder Deterministic Sort

**What:** `sort_key = (priority_rank, relation_rank, line_bucket, normalized_path)` 오름차순 정렬. `normalized_path`까지 포함해야 tie-break가 결정론적.

```python
# src/ddk/services/context_pack_builder.py
import math, hashlib, json
from pathlib import Path

_PRIORITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}

@dataclass
class _Candidate:
    path: str
    priority: str
    relation_rank: int    # exact symbol=1, same-dir sibling=2, shared=3
    content: str

    @property
    def line_count(self) -> int:
        return self.content.count("\n") + 1

    @property
    def sort_key(self) -> tuple[int, int, int, str]:
        return (
            _PRIORITY_RANK[self.priority],
            self.relation_rank,
            math.ceil(self.line_count / 50),   # line_bucket
            self.path.replace("\\", "/").lower(),  # normalized_path
        )

class ContextPackBuilder:
    MAX_FILES = 6
    MAX_LINES = 300

    def build(
        self,
        intent_graph: IntentGraph,
        repo_profile: RepoProfile,
        target_files: list[str],
        repo_path: Path,
    ) -> ContextPack:
        candidates = sorted(
            self._gather_candidates(intent_graph, repo_profile, target_files, repo_path),
            key=lambda c: c.sort_key,
        )
        selected = candidates[: self.MAX_FILES]
        # 300줄 초과 시 낮은 우선순위부터 제거 (P5→P4→P3→P2, P1은 synopsis-only로 축소)
        while self._total_lines(selected) > self.MAX_LINES and selected:
            selected.pop()
        return self._build_pack(selected, target_files)
```

### Anti-Patterns to Avoid

- **노드에 로직 직접 작성** (D-05): 서비스 레이어로 반드시 분리
- **`state["list"].append()`** : LangGraph 상태 불변 패턴 — 반드시 `{"field": new_value}` dict 반환
- **LLM 먼저 호출** (D-07): 정적 파싱으로 충분하면 LLM 미호출
- **`@pytest.mark.integration` 누락**: 실제 API 호출 테스트에 마커 필수
- **`model_dump()`에서 Python 기본 타입이 아닌 값 직접 JSON 직렬화**: `model_dump_json()` 또는 Pydantic 직렬화 사용

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON 스키마 강제 구조화 출력 | 자체 파싱 로직 | `ClaudeAdapter.complete_structured()` + `tool_use` | 이미 구현됨; tool_use가 JSON 스키마 준수 보장 |
| LLM 응답 Pydantic 파싱 | 커스텀 JSON 파서 | `Model.model_validate(json.loads(response.content))` | 스키마 drift 즉시 감지 (`extra="forbid"`) |
| 파일 존재 확인 | `os.path.exists()` | `Path.exists()` + try/except | Python 3.12 Path API |
| 이미지 해시 | 커스텀 해시 | `hashlib.sha256(bytes).hexdigest()[:16]` | 결정론적, 표준 |
| ContextPack tie-break | "좋은 감각" | `sort_key = (priority_rank, relation_rank, line_bucket, normalized_path)` | `24-context-pack-determinism.md` §3.2 |
| LLM error handling | 커스텀 retry | `node_wrapper()` OS/timeout 에러 바운더리 | 이미 구현됨 |

**Key insight:** Phase 1이 모든 인프라를 구축했다. Phase 2는 서비스 로직을 작성하고 기존 패턴을 재사용하는 것이 핵심이다.

---

## LLM Routing (확정된 라우팅 정책)

| 서비스 | 모델 | 이유 | 최대 토큰 |
|--------|------|------|-----------|
| `SemanticIntentExtractor` | `claude-3-5-sonnet-20241022` | vision + 복잡한 구조화 출력 | 4,096 |
| `DesignSystemInferencer` | `claude-3-5-sonnet-20241022` | 디자인 토큰 추론, 정확도 우선 | 2,048 |
| `RepoConventionScanner` (LLM 보완) | `claude-3-haiku-20240307` | 단순 패턴 분석, 비용 절감 | 2,048 |
| `GenerationPlanner` | `claude-3-5-sonnet-20241022` | 복잡한 계획 생성 | 3,072 |

**비용 예산 참고 (`11-llm-interface.md`):**
- Sonnet: $3.00/M input, $15.00/M output (1M tokens)
- Haiku: $0.25/M input, $1.25/M output
- 케이스당 비용 상한: `DDK_LLM_COST_CAP_USD=2.0`

---

## ServiceContainer 연결 (Phase 2에서 추가)

Phase 2에서 `ServiceContainer`에 서비스 어댑터를 등록하는 팩토리 함수를 추가해야 한다:

```python
# src/ddk/graph/context.py 또는 src/ddk/graph/factory.py
from ddk.services.intake_processor import IntakeProcessor
from ddk.services.repo_convention_scanner import RepoConventionScanner
from ddk.services.semantic_intent_extractor import SemanticIntentExtractor
from ddk.services.design_system_inferencer import DesignSystemInferencer
from ddk.services.generation_planner import GenerationPlanner
from ddk.services.context_pack_builder import ContextPackBuilder

@dataclass
class ServiceContainer:
    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    sandbox: SandboxAdapter
    build_runner: BuildRunner
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter
    # Phase 2 추가
    intake_processor: IntakeProcessor
    repo_convention_scanner: RepoConventionScanner
    semantic_intent_extractor: SemanticIntentExtractor
    design_system_inferencer: DesignSystemInferencer
    generation_planner: GenerationPlanner
    context_pack_builder: ContextPackBuilder

def create_production_container(api_key: str) -> ServiceContainer:
    llm = ClaudeAdapter(api_key=api_key)
    return ServiceContainer(
        llm=llm,
        ...,
        intake_processor=IntakeProcessor(),
        repo_convention_scanner=RepoConventionScanner(llm=llm),
        semantic_intent_extractor=SemanticIntentExtractor(llm=llm),
        design_system_inferencer=DesignSystemInferencer(llm=llm),
        generation_planner=GenerationPlanner(llm=llm),
        context_pack_builder=ContextPackBuilder(),
    )
```

**주의:** `ServiceContainer`를 `@dataclass`로 확장하면 기존 `tests/integration/test_di_smoke.py`의 `ServiceContainer` 생성 코드를 업데이트해야 한다.

---

## Common Pitfalls

### Pitfall 1: `tool_use` 응답 파싱 실패

**What goes wrong:** `ClaudeAdapter.complete_structured()`가 `ToolUseBlock`이 아닌 `TextBlock`을 반환하면 `_extract_tool_input()`이 `"{}"` 빈 딕트를 반환. `model_validate({})`가 필수 필드 ValidationError를 발생시킨다.

**Why it happens:** Claude가 `tool_choice={"type": "tool", "name": ...}`를 무시하고 텍스트 응답을 반환하는 경우 (드물지만 발생).

**How to avoid:** `_extract_tool_input()`의 `"{}"` fallback을 `LLMNonRetryableError`로 변경하거나, `model_validate` 실패 시 `safe_llm_call` 패턴으로 상태를 `manual-review-required`로 전환.

**Warning signs:** 단위 테스트가 통과했는데 통합 테스트에서 `ValidationError: X field required` 발생.

### Pitfall 2: `FakeLLMAdapter` key 미일치

**What goes wrong:** `FakeLLMAdapter._extract_key()`는 system 메시지의 **첫 번째 단어(소문자)**를 key로 사용한다. 서비스 프롬프트의 system message가 `"You are an expert..."` 이면 key는 `"you"`다.

**Why it happens:** FakeLLMAdapter 설계가 system prompt 첫 단어 기반이므로, 여러 서비스가 동일 key를 사용할 수 있다.

**How to avoid:** 각 서비스별 단위 테스트에서:
```python
# 잘못된 방법
fake_llm = FakeLLMAdapter(responses={"extract_intent": mock_intent_json})
# 올바른 방법
fake_llm = FakeLLMAdapter(responses={"you": mock_intent_json})
# 또는 FakeLLMAdapter를 확장하여 더 명확한 key 전략 사용
```

### Pitfall 3: LangGraph 상태 뮤테이션

**What goes wrong:** 노드가 `state["list"].append(item)`을 호출하면 LangGraph 상태가 오염됨.

**Why it happens:** Python list는 가변 참조.

**How to avoid:** 항상 새 딕트 반환:
```python
# 잘못된 방법
state["llm_call_records"].append(record_id)
return state

# 올바른 방법
return {
    "llm_call_records": [*state.get("llm_call_records", []), record_id],
    "current_node": "intent_extract",
}
```

### Pitfall 4: `RepoProfile.framework = "other"` 미처리

**What goes wrong:** 정적 파싱이 `package.json`을 찾지 못하면 `framework = "other"`. 이후 `GenerationPlanner`가 "other" 프레임워크에 대해 잘못된 계획을 생성.

**Why it happens:** 에이전트 재량으로 정해진 기본값이지만, 이를 LLM 보완으로 연결하지 않으면 누락.

**How to avoid:** `_needs_llm_supplement()`는 `framework == "other"` 이면 항상 `True` 반환.

### Pitfall 5: ContextPack `MAX_LINES=300` 오버플로우 미처리

**What goes wrong:** P1 파일 하나가 300줄을 넘으면 전체 pack이 예산 초과.

**Why it happens:** `24-context-pack-determinism.md §4.2 Case A` edge case.

**How to avoid:** P1 파일 > 300줄인 경우 `import block + referenced symbol window (±20 lines) + synopsis`만 포함하는 청킹 로직 필수.

---

## Code Examples

### LLM 구조화 출력 패턴 (ClaudeAdapter 실사용)

```python
# Source: src/ddk/adapters/llm/claude.py (Phase 1 구현됨)
# SemanticIntentExtractor에서의 사용 패턴
response = await self._llm.complete_structured(
    messages=messages,
    config=LLMCallConfig(
        model="claude-3-5-sonnet-20241022",
        temperature=0.0,
        max_tokens=4096,
    ),
    output_schema=IntentGraph,  # model_json_schema() + tool_use 강제
)
data = json.loads(response.content)
data["id"] = case_input.case_id  # 필수 필드 주입
data["source_image_hash"] = image_hash
intent_graph = IntentGraph.model_validate(data)
```

### 5-노드 builder.py 연결 (D-08)

```python
# src/ddk/graph/builder.py — Phase 2 완료 후
from ddk.graph.nodes.intake import intake_node
from ddk.graph.nodes.repo_scan import repo_scan_node
from ddk.graph.nodes.intent_extract import intent_extract_node
from ddk.graph.nodes.design_system import design_system_node
from ddk.graph.nodes.plan import plan_node

def build_ddk_graph() -> StateGraph:
    workflow = StateGraph(GraphState, context_schema=ServiceContainer)
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
    return workflow
```

### package.json 정적 파싱 패턴

```python
import json
from pathlib import Path

def _parse_package_json(pkg_path: Path) -> dict:
    if not pkg_path.exists():
        return {}
    try:
        return json.loads(pkg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def _detect_framework(pkg: dict) -> str:
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "next" in deps:
        return "next"
    if "react" in deps:
        return "react"
    if "vue" in deps:
        return "vue"
    if "svelte" in deps:
        return "svelte"
    return "other"
```

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (asyncio_mode = "auto") |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/services/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |
| Integration run | `uv run pytest tests/integration/ -m integration -x -q` |

**Baseline:** 207 tests currently pass (`uv run pytest tests/ -x -q` → 0.63s). All Phase 2 additions must maintain 207 passing.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File |
|--------|----------|-----------|-------------------|------|
| INGEST-02 | CaseInput 검증 + 이미지 경로 존재 확인 | unit | `uv run pytest tests/unit/services/test_intake_processor.py -x` | ❌ Wave 0 |
| INGEST-02 | 이미지 해시(SHA256[:16]) 계산 | unit | same | ❌ Wave 0 |
| INGEST-03 | package.json 정적 파싱 → framework 감지 | unit | `uv run pytest tests/unit/services/test_repo_convention_scanner.py -x` | ❌ Wave 0 |
| INGEST-03 | tsconfig.json 정적 파싱 → TypeScript 설정 | unit | same | ❌ Wave 0 |
| INGEST-03 | eslintrc/prettierrc 정적 파싱 | unit | same | ❌ Wave 0 |
| INGEST-03 | LLM 보완 (정적 미확인 패턴만) | unit (FakeLLM) | same | ❌ Wave 0 |
| INGEST-03 | fixture React/TS repo 분석 | integration | `uv run pytest tests/integration/ -m integration -k repo_scan` | ❌ Wave 0 |
| INGEST-04 | IntentGraph 구조화 출력 파싱 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_semantic_intent_extractor.py -x` | ❌ Wave 0 |
| INGEST-04 | 이미지 base64 인코딩 + Message 전달 | unit | same | ❌ Wave 0 |
| INGEST-04 | 실제 Claude API → IntentGraph | integration | `uv run pytest tests/integration/ -m integration -k intent_extract` | ❌ Wave 0 |
| INGEST-05 | DesignSystem 구조화 출력 파싱 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_design_system_inferencer.py -x` | ❌ Wave 0 |
| INGEST-05 | repo_profile.design_tokens 풍부화 | unit | same | ❌ Wave 0 |
| INGEST-06 | GenerationPlan 구조화 출력 파싱 | unit (FakeLLM) | `uv run pytest tests/unit/services/test_generation_planner.py -x` | ❌ Wave 0 |
| INGEST-06 | 동일 입력에 결정론적 plan 출력 | unit | same | ❌ Wave 0 |
| CODEGEN-03 | sort_key 우선순위 정렬 (P1>P5) | unit | `uv run pytest tests/unit/services/test_context_pack_builder.py -x` | ❌ Wave 0 |
| CODEGEN-03 | MAX_FILES=6, MAX_LINES=300 예산 준수 | unit | same | ❌ Wave 0 |
| CODEGEN-03 | tie-break: normalized_path lexical | unit | same | ❌ Wave 0 |
| CODEGEN-03 | insufficient_context=True 케이스 | unit | same | ❌ Wave 0 |
| CODEGEN-03 | context_pack_hash 결정론적 | unit | same | ❌ Wave 0 |
| D-08 | 5-노드 그래프 FakeLLM E2E | integration | `uv run pytest tests/integration/test_ingestion_pipeline.py -x` | ❌ Wave 0 |

### Unit Test Strategy (FakeLLMAdapter)

**핵심 패턴:** `FakeLLMAdapter`의 `_extract_key()`가 system 메시지 첫 번째 단어(소문자)를 key로 사용한다. 각 서비스의 system prompt 첫 단어를 key로 등록한다.

```python
# tests/unit/services/test_semantic_intent_extractor.py
import pytest
import json
from pathlib import Path
from tests.fakes import FakeLLMAdapter
from ddk.services.semantic_intent_extractor import SemanticIntentExtractor

@pytest.fixture
def mock_intent_response():
    return {
        "id": "C-001",
        "schema_version": "1.0",
        "source_image_hash": "abc123def456",
        "layout_regions": [...],
        "components": [...],
        "interactions": [],
        "confidence": 0.92,
    }

async def test_extract_intent_with_fake_llm(tmp_path, mock_intent_response):
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG\r\n...")
    fake_llm = FakeLLMAdapter(responses={"you": json.dumps(mock_intent_response)})
    # SemanticIntentExtractor system prompt starts with "You are..."
    extractor = SemanticIntentExtractor(llm=fake_llm)
    case_input = CaseInput(case_id="C-001", image_paths=[img], prompt="...", repo_path=tmp_path)
    result = await extractor.extract(case_input)
    assert result.confidence == 0.92
    assert len(fake_llm.call_log) == 1
```

**ContextPackBuilder 단위 테스트 (결정론적 검증):**
```python
async def test_context_pack_p1_before_p5(fixture_repo_path):
    builder = ContextPackBuilder()
    pack = builder.build(
        intent_graph=...,
        repo_profile=...,
        target_files=["src/App.tsx"],
        repo_path=fixture_repo_path,
    )
    priorities = [c.priority for c in pack.chunks]
    # P1이 P5보다 먼저
    assert priorities.index("P1") < priorities.index("P5")
    assert pack.total_lines <= 300

async def test_context_pack_deterministic_same_input(fixture_repo_path):
    builder = ContextPackBuilder()
    pack1 = builder.build(...)
    pack2 = builder.build(...)
    assert pack1.context_pack_hash == pack2.context_pack_hash
```

### Integration Test Strategy (@pytest.mark.integration)

```python
# tests/integration/test_ingestion_pipeline.py
@pytest.mark.integration
async def test_five_node_pipeline_with_fake_llm(tmp_path, service_container_with_fakes):
    """D-08: START → intake → repo_scan → intent_extract → design_system → plan → END"""
    img = tmp_path / "design.png"
    img.write_bytes(b"\x89PNG")
    (tmp_path / "package.json").write_text('{"dependencies": {"react": "^18"}}')

    case_input = CaseInput(
        case_id="C-001",
        image_paths=[img],
        prompt="쇼핑몰 메인 페이지",
        repo_path=tmp_path,
    )
    graph = build_ddk_graph().compile()
    result = await graph.ainvoke(
        initial_state(case_input),
        config={"configurable": {"langgraph_runtime": service_container_with_fakes}},
    )
    assert result["repo_profile"] is not None
    assert result["repo_profile"].framework == "react"
    assert result["intent_graph"] is not None
    assert result["generation_plan"] is not None
    assert result["terminal_state"] is None  # 정상 완료

@pytest.mark.integration
async def test_intent_extract_real_api(tmp_path, anthropic_api_key):
    """실제 Claude API 호출 — ANTHROPIC_API_KEY 필요"""
    # ... real API test ...
```

### Key Acceptance Criteria per Service

| Service | Acceptance Criteria |
|---------|---------------------|
| `IntakeProcessor` | CaseInput 반환; 이미지 미존재 시 `FileNotFoundError`; 이미지 5개 초과 시 `ValidationError` |
| `RepoConventionScanner` | React 프로젝트에서 `framework="react"` 반환; `package.json` 없으면 `framework="other"`; LLM 호출은 정적 불충분 시에만 |
| `SemanticIntentExtractor` | FakeLLM 응답에서 `IntentGraph` 파싱; `confidence >= 0.0`; `source_image_hash` 16자리 hex |
| `DesignSystemInferencer` | `DesignSystem` 반환; 이후 `repo_profile.design_tokens` 풍부화; FakeLLM으로 단위 테스트 통과 |
| `GenerationPlanner` | 동일 입력 → 동일 `GenerationPlan`; topological order 준수 |
| `ContextPackBuilder` | `total_lines <= 300`; `len(chunks) <= 6`; 동일 입력 → 동일 `context_pack_hash`; P1 없으면 `insufficient_context=True` |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/services/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate (D-08 완료 후):** `uv run pytest tests/ -x -q` + `uv run pytest tests/integration/test_ingestion_pipeline.py -x` 모두 green

### Wave 0 Gaps

- [ ] `src/ddk/services/__init__.py` — 서비스 레이어 패키지
- [ ] `tests/unit/services/__init__.py` — 서비스 단위 테스트 패키지
- [ ] `src/ddk/models/design_system.py` — `DesignSystem`, `InferredDesignToken` 모델
- [ ] `src/ddk/models/context_pack.py` — `ContextPack`, `ContextChunk` 모델
- [ ] `@pytest.mark.integration` 마커 설정 — `pyproject.toml` + `conftest.py`
- [ ] `Message` 이미지 지원 확장 — `src/ddk/adapters/llm/base.py`
- [ ] `ClaudeAdapter` 이미지 전송 지원 — `src/ddk/adapters/llm/claude.py`
- [ ] fixture repo 디렉토리: `tests/fixtures/repos/react-vite-ts/` (최소 package.json, tsconfig.json)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All services | ✓ | 3.12+ | — |
| `uv` | Package management | ✓ | — | — |
| `anthropic` SDK | ClaudeAdapter | ✓ (pyproject.toml) | ≥0.40.0 | — |
| `langgraph` | Graph builder | ✓ (pyproject.toml) | ≥1.0.0 | — |
| `ANTHROPIC_API_KEY` | Integration tests | 확인 필요 | — | skip via `@pytest.mark.integration` |

**Missing dependencies with no fallback:** 없음 (모든 패키지 Phase 1에서 설치됨).

**Missing dependencies with fallback:**
- `ANTHROPIC_API_KEY`: 없으면 integration test skip (unit test는 FakeLLM으로 항상 실행)

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OpenAI `response_format` JSON | Anthropic `tool_use` 구조화 출력 | 이 프로젝트 ADR-020 | ClaudeAdapter 이미 구현됨 |
| LLM-only repo scan | Static-first + LLM supplement (D-07) | Phase 2 설계 | 비용 절감, 예측 가능성 향상 |
| Monolithic node logic | Thin Node + Service Layer (D-05) | Phase 2 설계 | 서비스 독립 테스트 가능 |

---

## Open Questions

1. **`DesignSystem` 출력을 GraphState에 별도 필드로 추가할 것인가, 아니면 `repo_profile`을 업데이트할 것인가?**
   - What we know: 현재 GraphState에 `design_system` 필드 없음; 207개 테스트 통과 중
   - What's unclear: Phase 3 `generate` 노드가 DesignSystem 정보를 직접 읽어야 하는지
   - Recommendation: `repo_profile.design_tokens`를 풍부화하는 방식으로 **GraphState 변경 없이** 구현. Phase 3에서 필요하면 추가.

2. **`GenerationPlan` 스키마: 구현된 필드 vs 설계 문서 필드 중 어느 것을 따를 것인가?**
   - What we know: 구현된 `GenerationNode`에는 `target_path`, `node_type`이 없음; 설계 문서에는 있음
   - What's unclear: Phase 3 `CodeGenerator`가 어떤 필드를 읽는지 (`target_path`가 없으면 어디에 파일을 쓸지 모름)
   - Recommendation: **설계 문서의 `GenerationNode` 필드를 따르도록 모델을 업데이트**. `task_description` 대신 `target_path` + `node_type` 필드 사용.

3. **`FakeLLMAdapter`의 key 전략이 여러 서비스에서 충돌할 가능성**
   - What we know: 현재 system 메시지 첫 단어 기반 ("you" for most services)
   - What's unclear: 동일 key를 가진 두 서비스를 동시에 테스트할 때 충돌
   - Recommendation: `FakeLLMAdapter`에 `set_response_for_prompt(key, response)` 명시적 키 설정 메서드 추가 (또는 call index 기반 응답 순서 지정).

---

## Sources

### Primary (HIGH confidence)

- `src/ddk/adapters/llm/claude.py` — ClaudeAdapter 구현 (direct code inspection)
- `src/ddk/adapters/llm/base.py` — Message, LLMCallConfig, LLMResponse 타입 (direct code inspection)
- `src/ddk/graph/state.py` — GraphState 21 필드 (direct code inspection)
- `src/ddk/graph/nodes/_wrapper.py` — node_wrapper 패턴 (direct code inspection)
- `docs/design/11-llm-interface.md` — LLM 라우팅 정책, safe_llm_call 규칙
- `docs/design/16-prompt-design.md` — 모든 LLM 서비스의 system prompt 전체
- `docs/design/24-context-pack-determinism.md` — ContextPackBuilder 결정론적 알고리즘 완전 명세
- `docs/design/04-system-design.md` — 서비스 레이어 구현 계약, State Machine 흐름

### Secondary (MEDIUM confidence)

- `docs/design/12-data-models.md` — GenerationPlan 설계 문서 스키마 (구현과 불일치 발견됨)
- `docs/superpowers/plans/2026-03-27-ddalggak-sdd-tdd-implementation-plan.md` — Phase 2 작업 분해 참조

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Phase 1에서 이미 검증된 의존성만 사용
- Architecture patterns: HIGH — 설계 문서 + 구현된 코드 모두 확인
- Critical gaps: HIGH — 직접 코드 검사로 확인된 실제 미존재 항목
- Pitfalls: MEDIUM — Phase 1 코드 패턴에서 추론 + 설계 문서 기반

**Research date:** 2025-07-28
**Valid until:** 2025-08-28 (LangGraph/Anthropic API 변경 없으면 안정)

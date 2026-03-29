# Roadmap: 딸깍 (ddalggak)

## Overview

딸깍 v1.0 Delivery Pipeline MVP를 5단계로 구축한다. 아키텍처의 import 의존 체인(models → adapters → services → nodes → CLI)을 따라 바닥부터 쌓아 올린다. Phase 1에서 모든 기반 레이어(40+ Pydantic 모델, 7 Protocol, DI 컨테이너, 테스트 더블, 로깅, 워크스페이스)를 세우고, Phase 2~3에서 forward path(인제스트 → 분석 → 생성 → 정규화)를 완성한 뒤, Phase 4에서 가장 복잡한 검증·자동수정 루프를 구현하고, Phase 5에서 인증·CLI·E2E로 마무리한다. SDD+TDD 방법론을 적용하여 테스트를 먼저 작성하고 구현으로 통과시킨다.

## Phases

- [x] **Phase 1: Foundation & Core Infrastructure** - 모델, Protocol, DI, 테스트 더블, 로깅, 워크스페이스, 프리플라이트 — 모든 후속 Phase의 기반
- [x] **Phase 2: Ingestion & Analysis** - 디자인 시안 입력부터 생성 계획 그래프까지 5단계 분석 파이프라인 (completed 2026-03-28)
- [ ] **Phase 3: Code Generation & Normalization** - 생성 계획에서 코드 생성 후 레포 규칙에 맞게 정규화 — forward path 완성
- [ ] **Phase 4: Validation & Self-Healing** - 샌드박스 검증, 비주얼 리그레션, 실패 분류, 자동수정 루프 — 최고 위험/복잡도 Phase
- [ ] **Phase 5: Certification, CLI & E2E** - 증거팩, 스코어카드, 릴리즈 판정, LangGraph 통합, CLI 진입점, E2E 테스트

## Phase Details

### Phase 1: Foundation & Core Infrastructure
**Goal**: 모든 후속 Phase가 의존하는 기반 레이어를 구축한다 — 프로젝트 스캐폴딩, 40+ Pydantic 모델, 7개 어댑터 Protocol, ServiceContainer DI, 8개 테스트 더블, 구조화 로깅, 워크스페이스 관리, 프리플라이트 닥터, 샌드박스 정책 정의
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INGEST-01, VALID-06, CERT-04, CERT-05
**Success Criteria** (what must be TRUE):
  1. `uv run pytest` 실행 시 Ruff 린트 + Pyright 타입체크 통과; 40+ Pydantic v2 모델 전체가 roundtrip 직렬화 테스트(serialize → deserialize → equal) 통과 (12-data-models.md 기반)
  2. 7개 어댑터 Protocol (LLM, Filesystem, Git, Browser, BuildRunner, Subprocess, ScreenshotDiff)이 정의되어 있고, 각각 최소 1개 테스트 더블(FakeLLMAdapter 등)이 작동; chaos fixtures (malformed JSON, rate limit, extra fields)가 fault path를 검증
  3. ServiceContainer가 모든 fake 어댑터로 인스턴스화되고, LangGraph StateGraph의 `context_schema`를 통해 주입 가능 — 스모크 테스트 그래프 노드가 DI로 서비스 접근 성공
  4. `ddk doctor`가 환경 전제조건(Python 버전, uv, Playwright 브라우저, git, LLM API 키)을 점검하고 pass/fail 테이블 + 교정 힌트 출력
  5. `ddk init <case_id>`가 `.ddk/` 워크스페이스 디렉토리 구조를 생성하고 스키마 버전 파일 포함; structlog JSON 로그가 비밀정보 레닥션 적용; 샌드박스 실행 정책(ENV_WHITELIST, FORBIDDEN_READ_PATHS)이 정의되고 테스트로 검증 가능
**Plans**: 7 plans

Plans:
- [x] 01-01-PLAN.md — Project scaffolding: pyproject.toml, directory tree, DDKBaseModel, config, errors
- [x] 01-02-PLAN.md — Data models: CaseInput, RepoProfile, IntentGraph, Design Studio (18 models)
- [x] 01-03-PLAN.md — Data models: Pipeline & Output (16 models incl. LLMCallRecord)
- [x] 01-04-PLAN.md — 7 adapter Protocols + sandbox policy definitions
- [x] 01-05-PLAN.md — 8 test doubles (fakes) + chaos fixtures
- [x] 01-06-PLAN.md — GraphState TypedDict, ServiceContainer DI, structured logging, secret redaction
- [x] 01-07-PLAN.md — WorkspaceManager, PreflightDoctor, ddk CLI (doctor, init)

### Phase 2: Ingestion & Analysis
**Goal**: 디자인 시안(이미지+프롬프트)을 받아 5단계 분석(intake → repo scan → intent → design system → plan)을 거쳐 검증된 GenerationPlan을 출력한다 — 첫 LLM 호출 Phase로 비용 추적과 구조화 출력 파싱 패턴을 확립
**Depends on**: Phase 1
**Requirements**: INGEST-02, INGEST-03, INGEST-04, INGEST-05, INGEST-06, CODEGEN-03
**Success Criteria** (what must be TRUE):
  1. 이미지 + 프롬프트 입력 시 intake 노드가 검증된 CaseInput을 생성 — 이미지 참조와 프롬프트 텍스트가 올바르게 구조화됨
  2. Repo convention scanner가 샘플 React/TypeScript 프로젝트를 분석하여 프레임워크, 네이밍 규칙, 스타일링 방식, 파일 레이아웃을 포함한 RepoProfile 출력
  3. Semantic intent extractor가 IntentGraph(레이아웃/인터랙션/콘텐츠 인텐트 + confidence)를 생성하고, design system inferencer가 토큰/스페이싱/타이포그래피를 추론
  4. Generation planner가 ordered GenerationPlan 그래프(task 노드 + validation/repair 훅)를 출력 — 동일 입력에 대해 결정론적 결과
  5. Context pack builder가 결정론적 출력(최대 6파일/300줄, P1-P5 우선순위, 사전순 tie-break)을 생성하고 LLM 컨텍스트 예산 내 유지
**Plans**: 5 plans

Plans:
- [x] 02-01-PLAN.md — Wave 0 Infrastructure: DesignSystem/ContextPack models, Message image extension, ClaudeAdapter images, GenerationNode schema update, test infra, ServiceContainer extension, service stubs
- [x] 02-02-PLAN.md — IntakeProcessor service + intake_node, RepoConventionScanner service + repo_scan_node
- [x] 02-03-PLAN.md — SemanticIntentExtractor service + intent_extract_node, DesignSystemInferencer service + design_system_node
- [x] 02-04-PLAN.md — GenerationPlanner service + plan_node, ContextPackBuilder service
- [x] 02-05-PLAN.md — 5-node partial graph assembly (D-08), integration test with FakeLLM

### Phase 3: Code Generation & Normalization
**Goal**: GenerationPlan에서 빌드 가능한 React/TypeScript 코드를 생성하고, 타겟 레포 규칙에 맞게 정규화하여 forward path(intake→certify 이전까지)를 완성한다
**Depends on**: Phase 2
**Requirements**: CODEGEN-01, CODEGEN-02
**Success Criteria** (what must be TRUE):
  1. Code generator가 GenerationPlan에서 GeneratedArtifactSet(컴포넌트/페이지 파일 + 파일 맵 + 생성 트레이스)을 생성 — 출력이 유효한 TypeScript/React로 컴파일 가능
  2. Post-generation normalizer가 생성 코드를 RepoProfile 규칙(네이밍, 임포트, 디자인 토큰, 파일 배치)에 맞게 정규화하고, 적용된 모든 변환을 기록한 NormalizationReport 출력
  3. 6-노드 서브그래프(ingest → repo_scan → intent → plan → generate → normalize)를 FakeLLM으로 end-to-end 실행 시 각 노드에서 올바른 아티팩트 생성
**Plans**: 4 plans

Plans:
- [x] 03-00-PLAN.md — Wave 0: Model alignment — align GeneratedArtifactSet, GeneratedFile, NormalizationReport, ConventionFix with design spec (additive only)
- [x] 03-01-PLAN.md — Wave 1: CodeGenerator service + generate_node (CODEGEN-01)
- [x] 03-02-PLAN.md — Wave 2: OutputNormalizer service + normalize_node (CODEGEN-02)
- [ ] 03-03-PLAN.md — Wave 3: 7-node graph assembly + E2E integration tests

### Phase 4: Validation & Self-Healing
**Goal**: 생성된 코드를 격리 샌드박스에서 자동 검증하고, 실패를 분류하여 결정론적 규칙 기반 패치를 적용한 뒤 예산 내에서 재검증한다 — 실패 시 체크포인트 롤백
**Depends on**: Phase 3
**Requirements**: VALID-01, VALID-02, VALID-03, VALID-04, VALID-05, VALID-07
**Success Criteria** (what must be TRUE):
  1. 생성 코드가 git worktree 샌드박스에서 빌드/타입체크/린트/런타임 스모크 테스트를 실행하고 RuntimeValidationReport를 출력 — 호스트 환경과 완전 격리
  2. Playwright가 브라우저 콘솔 에러, 런타임 예외, 실패 네트워크 요청을 상관 ID로 수집; SSIM 비주얼 비교가 diff score와 mismatch 영역을 포함한 VisualRegressionReport 출력
  3. FailureClassifier가 모든 실패에 안정 taxonomy ID(build/type/runtime/visual/data-binding/async)를 부여하고, AutoFixPlanner가 9개 수리 규칙에서 올바른 규칙을 선택
  4. 자동수정 루프가 패치 적용 → 재검증 → 3회 retry 예산 준수; 진동 감지(A→B→A) 시 즉시 중단; 각 시도마다 git 체크포인트(refs/ddk/fix/{case_id}/attempt-{n}) 생성, 실패 시 자동 롤백
  5. 실패 없는 케이스는 검증 통과; 수정 가능한 실패는 자동수정 트리거; retry 예산 초과 시 taxonomy ID가 포함된 명확한 실패 리포트 출력
**Plans**: TBD

### Phase 5: Certification, CLI & E2E
**Goal**: 파이프라인 전체를 LangGraph 10-노드 그래프로 조립하고, 증거팩·스코어카드·릴리즈 판정을 구현한 뒤, `ddk` CLI 진입점과 E2E 테스트로 v1.0을 마무리한다
**Depends on**: Phase 4
**Requirements**: CERT-01, CERT-02, CERT-03, CERT-06, CERT-07
**Success Criteria** (what must be TRUE):
  1. EvidencePack이 모든 단계 아티팩트(로그, 리포트, 스크린샷, diff)를 리플레이 가능한 패키지로 번들링 — LLM 호출 메타데이터(모델, provider, temperature, seed, 스키마 버전, context pack hash) 포함
  2. Benchmark scorecard가 precision/maintainability/automation/scalability 점수를 계산하고, release decision gate가 critical/blocker 집계 + scorecard로 ready/blocked/manual-review 판정 출력
  3. `build_ddk_graph()`가 전체 10-노드 LangGraph StateGraph를 conditional edges, 상태 전이, _node_wrapper 에러 바운더리와 함께 구성 — 그래프 토폴로지 테스트 통과
  4. `ddk run <image> --prompt "..."`가 전체 파이프라인을 end-to-end 실행; `ddk rollback`, `ddk status`, `ddk certify` 서브커맨드 작동; 실패 시 non-zero exit code 반환
  5. FakeLLM + fixture repo로 전체 파이프라인(intake → release decision) E2E 테스트 실행 시 유효한 EvidencePack 생성 확인
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Core Infrastructure | 7/7 | Complete | 2026-03-27 |
| 2. Ingestion & Analysis | 5/5 | Complete ✅ verified | 2026-03-28 |
| 3. Code Generation & Normalization | 3/4 | In Progress|  |
| 4. Validation & Self-Healing | 0/TBD | Not started | - |
| 5. Certification, CLI & E2E | 0/TBD | Not started | - |

# Requirements: 딸깍 (ddalggak)

**Defined:** 2026-03-27
**Core Value:** Evidence-gated delivery — 증거 없이는 어떤 코드도 "완성"으로 인정하지 않는다.

## v1 Requirements

Requirements for Milestone v1.0 (Delivery Pipeline MVP). Each maps to roadmap phases.

### Foundation & Infrastructure

- [x] **INFRA-01**: 프로젝트 스캐폴딩 — pyproject.toml (uv), src 레이아웃, pytest/Ruff/Pyright 설정, CI 기본 구성
- [x] **INFRA-02**: Pydantic v2 데이터 모델 구현 — 40+ 모델 (CaseInput, RepoProfile, IntentGraph, GenerationPlan, GeneratedArtifactSet, NormalizationReport, RuntimeValidationReport, VisualRegressionReport, FixAttempt, Scorecard, ReleaseDecision, EvidencePack 등) — 12-data-models.md 기반
- [x] **INFRA-03**: 어댑터 Protocol 정의 — LLMAdapter, FilesystemAdapter, GitAdapter, BrowserAdapter, BuildRunnerAdapter, SubprocessAdapter 인터페이스
- [ ] **INFRA-04**: ServiceContainer + LangGraph context_schema DI 패턴 — 모든 노드가 서비스를 주입받는 런타임 컨텍스트 구성
- [ ] **INFRA-05**: 테스트 인프라 — FakeLLMAdapter, TempDirSandbox, FakePlaywrightAdapter, FakeSubprocessRunner 등 8개 fake + chaos fixtures (malformed JSON, rate limit, extra fields)
- [ ] **INFRA-06**: 구조화 로그 — structlog + RedactingFormatter + JSON 출력, 12개 필수 로그 이벤트 (04-system-design.md § 구조화 로그 명세)

### Ingestion & Analysis

- [ ] **INGEST-01**: Workspace Bootstrap (DDK-REQ-001) — 케이스 워크스페이스 초기화, .ddk/ 디렉토리 구조, 스키마 버전 관리
- [x] **INGEST-02**: Multimodal Intake (DDK-REQ-002) — 이미지/프롬프트/레퍼런스 텍스트를 CaseInput으로 검증·구조화
- [x] **INGEST-03**: Repo Convention Scan (DDK-REQ-003) — RepoConventionScanner 서비스, 프레임워크/네이밍/스타일/디자인 시스템/파일 레이아웃 추출 → RepoProfile
- [x] **INGEST-04**: Semantic Intent Model (DDK-REQ-004) — SemanticIntentExtractor, 레이아웃/인터랙션/콘텐츠 인텐트를 confidence graph로 추출 → IntentGraph
- [x] **INGEST-05**: Design System Inference (DDK-REQ-005) — DesignSystemInferencer, 토큰/스페이싱/타이포그래피/재사용 프리미티브 추론
- [x] **INGEST-06**: Generation Plan Graph (DDK-REQ-006) — GenerationPlanner, 작업을 ordered graph로 분해, output/validate/repair 훅 포함 → GenerationPlan

### Code Generation & Normalization

- [x] **CODEGEN-01**: Code Generation Engine (DDK-REQ-007) — CodeGenerator 서비스, 컴포넌트/페이지 코드 생성, 파일 맵 및 트레이스 → GeneratedArtifactSet
- [x] **CODEGEN-02**: Post-generation Normalizer (DDK-REQ-008) — OutputNormalizer, 네이밍/임포트/토큰/파일배치 드리프트를 RepoProfile 기반으로 정규화 → NormalizationReport
- [x] **CODEGEN-03**: Context Pack Builder (DDK-REQ-015 일부) — ContextPackBuilder, 최대 6파일/300줄, P1~P5 우선순위, 사전순 tie-break, 결정론적 출력

### Validation & Self-Healing

- [ ] **VALID-01**: Sandboxed Runtime Validation (DDK-REQ-009) — git worktree 샌드박스에서 빌드/타입체크/린트/런타임 스모크 실행 → RuntimeValidationReport
- [ ] **VALID-02**: Console & Runtime Error Capture (DDK-REQ-010) — Playwright 기반 브라우저 콘솔, 런타임 예외, 실패 요청을 상관 ID로 수집
- [ ] **VALID-03**: Visual Regression Runner (DDK-REQ-011) — 레퍼런스 vs 생성 스크린샷 SSIM 비교, diff score/mismatch 영역 출력 → VisualRegressionReport
- [ ] **VALID-04**: Bounded Auto-fix Loop (DDK-REQ-012) — AutoFixPlanner + 9개 수리 규칙, 실패 클래스별 패치 생성, 최대 3회 재시도, 진동 감지
- [ ] **VALID-05**: Failure Taxonomy (DDK-REQ-013) — FailureClassifier, 빌드/타입/런타임/비주얼/데이터바인딩/비동기 실패를 안정 taxonomy ID로 분류
- [x] **VALID-06**: Sandboxed Execution Policy (DDK-REQ-016) — ENV_WHITELIST 허용목록, FORBIDDEN_READ_PATHS, 프로세스 격리 규칙 적용
- [ ] **VALID-07**: Auto-fix Rollback & Checkpoint (DDK-REQ-019) — RollbackController, git 체크포인트 (refs/ddk/fix/{case_id}/attempt-{n}), 실패 시 자동 롤백

### Certification & CLI

- [ ] **CERT-01**: Evidence Pack Builder (DDK-REQ-014) — EvidencePackBuilder, 각 단계 아티팩트/로그/리포트 번들, 리플레이 가능 → EvidencePack
- [ ] **CERT-02**: Comparative Benchmark & Scorecard (DDK-REQ-017) — BenchmarkScorecardService, precision/maintainability/automation/scalability 점수 출력 → Scorecard
- [ ] **CERT-03**: Release Decision / Perfection Gate (DDK-REQ-018) — ReleaseDecisionService, critical/blocker/scorecard 집계 → ReleaseDecision (ready/blocked/manual-review)
- [x] **CERT-04**: Reproducibility & LLM Call Metadata (DDK-REQ-020) — LLMCallRecord, 모델/provider/temperature/seed/스키마 버전 기록, context pack hash
- [ ] **CERT-05**: Preflight Doctor & Guided Setup (DDK-REQ-021) — PrefightDoctor, 환경 전제조건 사전 점검 (빌드 도구, LLM 키, Playwright, 샌드박스), 교정 힌트 출력
- [ ] **CERT-06**: LangGraph 오케스트레이션 통합 (DDK-REQ-015 나머지) — build_ddk_graph(), GraphState 전이, _node_wrapper, conditional edges, 상태 추적
- [ ] **CERT-07**: ddk CLI 엔트리포인트 + E2E 통합 — Typer 기반 ddk run/preflight/status/rollback/certify 커맨드, 전체 파이프라인 E2E 테스트

## v2 Requirements

Deferred to Milestone v2.0 (Design Studio).

### Design Studio
- [ ] **STUDIO-01**: Requirements Elicitation (DDK-REQ-022) — 자연어 입력 + 인터뷰 기반 구조화 요구사항 도출
- [ ] **STUDIO-02**: Standard-Compliant Doc Synthesis (DDK-REQ-023) — 10종 설계 문서 자동 생성
- [ ] **STUDIO-03**: Quality Gate & Consistency Check (DDK-REQ-024) — 설계 패키지 완성도/일관성/AI 구현성 자동 평가

## v3 Requirements

Deferred to Milestone v3.0 (Multi-tool Adapter).

### Multi-tool Adapter
- [ ] **ADAPTER-01**: Claude Code Adapter (DDK-REQ-025)
- [ ] **ADAPTER-02**: GitHub Copilot Adapter (DDK-REQ-026)
- [ ] **ADAPTER-03**: Gemini CLI Adapter (DDK-REQ-027)
- [ ] **ADAPTER-04**: OpenCode & Codex Adapter (DDK-REQ-028)
- [ ] **ADAPTER-05**: MCP Server (DDK-REQ-029)

## Out of Scope

- **GUI/웹 대시보드** — CLI-first 접근, UI는 향후 고려
- **GSD 워크플로우 계승** — v1.0은 Delivery Pipeline에 집중
- **실시간 스트리밍 UI** — 경쟁사 anti-feature (v0/bolt.new), CLI 도구에 불필요
- **멀티페이지 앱 생성** — 단일 컴포넌트/페이지에 집중
- **자체 호스팅 LLM** — 클라우드 API (Anthropic/OpenAI)만 지원

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Complete |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |
| INFRA-06 | Phase 1 | Pending |
| INGEST-01 | Phase 1 | Pending |
| INGEST-02 | Phase 2 | Complete |
| INGEST-03 | Phase 2 | Complete |
| INGEST-04 | Phase 2 | Complete |
| INGEST-05 | Phase 2 | Complete |
| INGEST-06 | Phase 2 | Complete |
| CODEGEN-01 | Phase 3 | Complete |
| CODEGEN-02 | Phase 3 | Complete |
| CODEGEN-03 | Phase 2 | Complete |
| VALID-01 | Phase 4 | Pending |
| VALID-02 | Phase 4 | Pending |
| VALID-03 | Phase 4 | Pending |
| VALID-04 | Phase 4 | Pending |
| VALID-05 | Phase 4 | Pending |
| VALID-06 | Phase 1 | Complete |
| VALID-07 | Phase 4 | Pending |
| CERT-01 | Phase 5 | Pending |
| CERT-02 | Phase 5 | Pending |
| CERT-03 | Phase 5 | Pending |
| CERT-04 | Phase 1 | Complete |
| CERT-05 | Phase 1 | Pending |
| CERT-06 | Phase 5 | Pending |
| CERT-07 | Phase 5 | Pending |

---

*Last updated: 2025-07-27*

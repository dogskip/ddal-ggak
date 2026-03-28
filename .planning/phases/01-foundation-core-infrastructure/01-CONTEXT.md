# Phase 1: Foundation & Core Infrastructure - Context

**Gathered:** 2025-07-27
**Status:** Ready for planning

<domain>
## Phase Boundary

모든 후속 Phase가 의존하는 기반 레이어를 구축한다 — 프로젝트 스캐폴딩, 40+ Pydantic v2 모델, 7개 어댑터 Protocol, ServiceContainer DI, 8개 테스트 더블, 구조화 로깅, 워크스페이스 관리, 프리플라이트 닥터, 샌드박스 정책 정의.

**Requirements:** INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05, INFRA-06, INGEST-01, VALID-06, CERT-04, CERT-05

</domain>

<decisions>
## Implementation Decisions

### DI 패턴
- **D-01:** LangGraph `context_schema` + `Runtime[ServiceContainer]` 패턴을 채택한다. 설계 문서 원본의 `.from_config()` 팩토리 패턴은 사용하지 않는다. `ServiceContainer`는 `@dataclass`로 정의하며, 모든 어댑터 Protocol 인스턴스를 보유한다. 노드는 `runtime: Runtime[ServiceContainer]` 파라미터로 서비스에 접근한다. 테스트 시 fake 어댑터로 구성된 `ServiceContainer`를 주입하여 격리 테스트를 수행한다.

### 모델 구현 범위
- **D-02:** `12-data-models.md`에 정의된 40+ Pydantic v2 모델을 전부 Phase 1에서 구현한다. 각 모델에 대해 roundtrip 직렬화 테스트(serialize → deserialize → assert equal)를 작성한다. 이를 통해 전체 시스템의 데이터 계약을 Phase 1에서 확립하고, 후속 Phase에서 모델 변경 없이 서비스/노드 구현에 집중한다.

### TDD 실행 순서
- **D-03:** Bottom-up TDD를 적용한다. 빌드 순서: (1) Pydantic 모델 + roundtrip 테스트 → (2) 7개 어댑터 Protocol 정의 + 프로토콜 적합성 테스트 → (3) 8개 테스트 더블(FakeLLM 등) + fake 동작 테스트 → (4) ServiceContainer + DI 스모크 테스트 → (5) 워크스페이스/프리플라이트/로깅 서비스 + 서비스 단위 테스트 → (6) CLI 진입점(ddk doctor, ddk init) + CLI 통합 테스트.

### Git 연동 방식
- **D-04:** 하이브리드 접근을 채택한다. 읽기 작업(log, diff, status, blame)은 GitPython(`Repo` 객체) 사용, 쓰기/worktree/checkpoint 작업은 `asyncio.create_subprocess_exec()`로 git CLI를 직접 호출한다. GitPython `Repo` 객체는 반드시 명시적으로 `close()`하거나 context manager로 사용하여 프로세스 누수를 방지한다.

### 에이전트 재량 영역
- 파일 내부 모듈 분할 (파일 당 모델 수, 유틸리티 분리 등)은 에이전트가 `13-project-structure.md`를 따라 자율 결정
- conftest.py 구조와 fixture 계층은 에이전트가 pytest best practice에 따라 자율 결정
- Ruff/Pyright 설정 세부 규칙은 에이전트가 `03-constraints-nfr.md` 범위 내에서 자율 결정

</decisions>

<specifics>
## Specific Ideas

- SDD+TDD 방법론: 테스트를 먼저 작성하고, 구현으로 테스트를 통과시키는 Red-Green-Refactor 사이클
- LangGraph 상태 뮤테이션 규칙 엄격 적용: `state["list"].append()` 금지, `state["list"] + [item]` 패턴만 허용 — 이를 검증하는 계약 테스트 포함
- FakeLLM은 Phase 0 인프라: 후속 모든 Phase의 TDD가 이에 의존하므로, 구조화 출력(JSON schema) 응답 시뮬레이션까지 지원해야 함
- structlog로 로깅 통일: CLI 스펙(structlog)과 보안 문서(stdlib)의 불일치를 structlog가 stdlib 핸들러를 래핑하는 방식으로 해결
- 비밀정보 레닥션: RedactingFormatter가 7개 정규식 패턴(`sk-`, `Bearer`, API key 등)을 적용하여 로그 출력 전 마스킹

</specifics>

<canonical_refs>
## Canonical References

**다운스트림 에이전트는 계획 또는 구현 전에 반드시 아래 문서를 읽어야 한다.**

### 프로젝트 구조 & 스캐폴딩
- `docs/design/13-project-structure.md` — 전체 src/ddk/ 디렉토리 구조, GraphState TypedDict 정의, 모듈별 책임
- `docs/design/03-constraints-nfr.md` — NFR 정량 목표, Ruff/Pyright 설정 기준, 성능 제약

### 데이터 모델
- `docs/design/12-data-models.md` — 40+ Pydantic v2 모델 전체 정의 (필드, 타입, 제약조건, enum, 관계)
- `docs/design/04-system-design.md` §예외 처리 규칙 — 비LLM 노드 예외 처리 테이블, 구조화 로그 명세

### 어댑터 Protocol & DI
- `docs/design/10-multi-tool-adapter.md` — 7개 어댑터 Protocol 정의, MCP 인증 정책, 도구 반환 스키마
- `docs/design/05-adr-set.md` ADR-004 — DI 컨테이너 결정 (context_schema로 업데이트 필요)
- `.planning/research/ARCHITECTURE.md` — LangGraph v1.1.3 context_schema + Runtime[T] 패턴 검증 결과

### 테스트 더블 & 모킹
- `docs/design/09-ai-handoff.md` §통합 테스트 모킹 전략 — 8개 Fake 구현 명세, 레이어별 모킹 테이블
- `docs/design/05-adr-set.md` ADR-019 — FakeLLM 전략 결정

### 로깅 & 보안
- `docs/design/04-system-design.md` §구조화 로그 명세 — structlog JSON 포맷, 필드 정의
- `docs/design/33-security-privacy-governance.md` §Redaction 구현 명세 — 7개 정규식 패턴, RedactingFormatter, Pydantic 어노테이션
- `docs/design/05-adr-set.md` ADR-014 — 로깅 라이브러리 결정

### 워크스페이스 & CLI
- `docs/design/14-cli-spec.md` §ddk init, §ddk doctor — CLI 서브커맨드 명세, 출력 형식
- `docs/design/14-cli-spec.md` §7 워크스페이스 — `.ddk/` 디렉토리 구조, 스키마 버전 관리

### 샌드박스 정책
- `docs/design/04-system-design.md` — 샌드박스 실행 환경 제약
- `docs/design/03-constraints-nfr.md` — ENV_WHITELIST, FORBIDDEN_READ_PATHS 정의

### LLM 호출 기록
- `docs/design/12-data-models.md` LLMCallRecord — 재현성 메타데이터 (모델, provider, temperature, seed, 스키마 버전, context pack hash)

### 리서치 결과
- `.planning/research/SUMMARY.md` — 스택, 아키텍처, 피트폴 종합
- `.planning/research/PITFALLS.md` — 12개 치명적 피트폴과 방지 전략 (특히 #1 상태 뮤테이션, #4 프로세스 누수)
- `.planning/research/STACK.md` — 10개 런타임 의존성, 버전 제약

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 없음 — 순수 그린필드 프로젝트. 코드 0줄 상태에서 시작.

### Patterns to Follow
- LangGraph `context_schema` DI 패턴 (리서치에서 검증됨)
- Pydantic v2 `model_validate` / `model_dump` roundtrip 패턴
- structlog `bind()` 기반 per-node 컨텍스트 로깅

### Patterns to Avoid
- `state["list"].append()` (LangGraph 상태 뮤테이션 오염 — 반드시 불변 패턴 사용)
- `.from_config()` 팩토리 (설계 문서 원본이지만 context_schema로 대체 결정)
- GitPython `Repo` 객체 미해제 (프로세스 누수 위험)

</code_context>

<deferred>
## Deferred Ideas

- Design Studio 그래프 (`build_design_studio_graph()`) — Phase 4+ / Milestone v2.0
- MCP 서버 통합 — Milestone v3.0
- Multi-provider LLM fallback 실제 호출 — Phase 2에서 구현 (Phase 1은 Protocol만 정의)
- Playwright 실제 브라우저 통합 — Phase 4
- SSIM 비주얼 비교 — Phase 4

</deferred>

---

*Phase: 01-foundation-core-infrastructure*
*Context gathered: 2025-07-27*

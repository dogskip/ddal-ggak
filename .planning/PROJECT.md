# 딸깍 (ddalggak)

## What This Is

딸깍은 디자인 시안(이미지+프롬프트)을 받아 프론트엔드 코드를 생성·검증·자동수정·인증까지 closed-loop으로 수행하는 Design-to-Delivery CLI 도구다. Python 3.12+ 기반이며, LangGraph 상태 머신으로 10단계 파이프라인을 오케스트레이션한다. 개발자가 `ddk run` 한 번으로 빌드 가능한 코드를 받는 것이 목표다.

## Core Value

**Evidence-gated delivery** — 생성된 코드가 빌드·타입체크·런타임·비주얼 회귀를 모두 통과해야만 릴리즈한다. 증거 없이는 어떤 코드도 "완성"으로 인정하지 않는다.

## Requirements

### Validated

(None yet — ship to validate)

### Active

#### Delivery Pipeline (P0 — Milestone v1.0)

- [ ] **DDK-REQ-001**: Workspace Bootstrap — 케이스 워크스페이스 초기화 및 스키마 버전 관리
- [ ] **DDK-REQ-002**: Multimodal Intake — 이미지/프롬프트/레퍼런스 텍스트를 검증된 입력 아티팩트로 구조화
- [ ] **DDK-REQ-003**: Repo Convention Scan — 프레임워크, 네이밍, 스타일, 디자인 시스템, 파일 레이아웃 추출
- [ ] **DDK-REQ-004**: Semantic Intent Model — 레이아웃/인터랙션/콘텐츠 인텐트를 confidence graph로 추출
- [ ] **DDK-REQ-005**: Design System Inference — 토큰, 스페이싱, 타이포그래피, 재사용 프리미티브 추론
- [ ] **DDK-REQ-006**: Generation Plan Graph — 작업을 ordered graph로 분해, output/validate/repair 훅 포함
- [ ] **DDK-REQ-007**: Code Generation Engine — 컴포넌트/페이지 코드 생성, 파일 맵 및 트레이스 포함
- [ ] **DDK-REQ-008**: Post-generation Normalizer — 네이밍/임포트/토큰/파일배치 드리프트를 레포 규칙에 맞게 정규화
- [ ] **DDK-REQ-009**: Sandboxed Runtime Validation — 빌드, 타입체크, 린트, 런타임 스모크를 격리 환경에서 실행
- [ ] **DDK-REQ-010**: Console & Runtime Error Capture — 브라우저 콘솔, 런타임 예외, 실패 요청을 상관 ID로 수집
- [ ] **DDK-REQ-011**: Visual Regression Runner — 레퍼런스 vs 생성 스크린샷 비교, diff score/mismatch 영역 출력
- [ ] **DDK-REQ-012**: Bounded Auto-fix Loop — 실패 클래스별 패치 생성 및 retry 예산 내 재검증
- [ ] **DDK-REQ-013**: Failure Taxonomy — 빌드/타입/런타임/비주얼/데이터바인딩/비동기 실패를 안정 taxonomy ID로 분류
- [ ] **DDK-REQ-014**: Evidence Pack Builder — 각 단계 아티팩트/로그/리포트 번들, 리플레이 가능
- [ ] **DDK-REQ-015**: LangGraph State & Context Orchestration — 명시적 그래프 상태 및 budgeted context pack 관리
- [ ] **DDK-REQ-016**: Sandboxed Execution Policy — 생성 코드 실행의 허용 범위 및 격리 규칙 적용
- [ ] **DDK-REQ-017**: Comparative Benchmark & Scorecard — precision/maintainability/automation/scalability 점수 출력
- [ ] **DDK-REQ-018**: Release Decision / Perfection Gate — critical/blocker/scorecard 집계, ready/blocked/manual-review 판정
- [ ] **DDK-REQ-019**: Auto-fix Rollback & Checkpoint — 자동수정 전 git 체크포인트, 실패 시 롤백
- [ ] **DDK-REQ-020**: Reproducibility & LLM Call Metadata — 모델/provider/temperature/seed/스키마 버전 기록
- [ ] **DDK-REQ-021**: Preflight Doctor & Guided Setup — 환경 전제조건 사전 점검, 교정 힌트 출력

### Out of Scope

- **DDK-REQ-022~024 (Design Studio)** — Phase 4 범위. Milestone v2.0에서 다룸
- **DDK-REQ-025~029 (Multi-tool Adapter + MCP)** — Phase 5 범위. Milestone v3.0에서 다룸
- **GSD 워크플로우 계승** — 딸깍의 정체성 축이지만 v1.0은 Delivery Pipeline에 집중
- **GUI/웹 대시보드** — CLI-first 접근. UI는 향후 고려

## Context

- **설계 문서 완비:** `docs/design/` 하위에 35개 설계 문서 존재 (PRD, 시스템 설계, ADR 26개, 데이터 모델, CLI 스펙, 보안, 테스트 전략 등)
- **독립 감사 완료:** 2026-03-27 독립 설계 감사 점수 95/100, "구현 승인 가능" 판정
- **구현 방법론:** SDD (Specification-Driven Development) + TDD (Test-Driven Development)
  - 각 Phase는 설계 스펙에서 직접 파생
  - 테스트를 먼저 작성하고 구현으로 통과시킴
- **코드 없음:** 현재 순수 설계 패키지 상태. 코드 0줄
- **모든 ADR Accepted:** 26개 아키텍처 결정이 승인 상태

## Constraints

- **Language**: Python 3.12+ — 설계 문서 전체가 Python 기반으로 작성됨
- **Package Manager**: uv — pip/poetry 대신 uv 사용 (ADR-015)
- **CLI Framework**: Typer — Click 기반, 16+ 서브커맨드 (ADR-012)
- **Data Validation**: Pydantic v2 — 40+ 모델 정의 완료 (12-data-models.md)
- **Orchestration**: LangGraph — StateGraph 기반 상태 머신 (ADR-010)
- **Browser Automation**: Playwright Python — 스크린샷, 콘솔 캡처 (ADR-014)
- **Visual Diff**: scikit-image SSIM — 구조 유사도 비교 (ADR-016)
- **Linting**: Ruff + Pyright — strict mode
- **Testing**: pytest — SDD+TDD 기반
- **Sandbox**: git worktree — 임시 작업 격리 (ADR-018)
- **Cost**: P0 단일 케이스 ≤ $0.10 (Claude Sonnet 기준)
- **Performance**: P0 단일 케이스 ≤ 120s (simple), ≤ 300s (with auto-fix)

## Key Decisions

- **ADR-010**: LangGraph StateGraph 채택 (DAG 기반, 명시적 상태 전이)
- **ADR-012**: Typer CLI 프레임워크 채택 (Click 래핑, 타입 힌트 활용)
- **ADR-014**: Playwright Python 채택 (빌드 후 스크린샷 + 콘솔 캡처)
- **ADR-015**: uv 패키지 매니저 채택 (설치 속도 + 재현성)
- **ADR-016**: scikit-image SSIM 채택 (결정론적 비주얼 비교)
- **ADR-018**: git worktree 샌드박스 채택 (경량 격리)
- **ADR-020**: Redaction by Default (비밀정보 마스킹 우선)
- **Auto-fix**: 결정론적 규칙 기반 (LLM 재프롬프팅 아님), 최대 3회 재시도, 9개 수리 규칙
- **Context Pack**: 최대 6파일 / 300줄, P1~P5 우선순위, 사전순 tie-break
- **인터뷰 예산**: P0 기본 5턴 (MAX_TURNS_P0 = 5)

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone:**
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---

*Last updated: 2026-03-27*

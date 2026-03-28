# Phase 1: Foundation & Core Infrastructure - Discussion Log

**Date:** 2025-07-27
**Participants:** User, GSD Agent
**Mode:** Interactive discussion (4 gray areas)

## Gray Areas Identified

| # | 영역 | 상태 |
|---|---|---|
| 1 | DI 패턴 선택 | ✅ 결정됨 |
| 2 | 모델 구현 범위 | ✅ 결정됨 |
| 3 | TDD 실행 전략 | ✅ 결정됨 |
| 4 | Git 연동 방식 | ✅ 결정됨 |

## Discussion Details

### 1. DI 패턴 선택

**제시된 옵션:**
- A) LangGraph `context_schema` + `Runtime[T]` — 리서치 권장, v1.1.3에서 검증됨, 테스트 시 fake 교체 용이
- B) 설계 문서 원본 `.from_config()` 팩토리 — 변경 최소화

**사용자 결정:** A) `context_schema` 채택

**근거:** 리서치에서 실제 LangGraph v1.1.3 API로 검증된 현대적 패턴. 테스트 더블 주입이 자연스럽고, 설계 문서의 DI 의도를 더 깔끔하게 구현.

**영향:** `05-adr-set.md` ADR-004를 context_schema 방식으로 업데이트 필요. 모든 노드 시그니처에 `runtime` 파라미터 추가.

### 2. 모델 구현 범위

**제시된 옵션:**
- A) 40+ 모델 전부 Phase 1에서 구현 — 데이터 계약 조기 확립, 후속 Phase 안정성
- B) Phase별 필요 모델만 점진 추가 — Phase 1 경량화, 단 모델 간 의존성 관리 복잡

**사용자 결정:** A) 전부 Phase 1

**근거:** Bottom-up 빌드 전략과 일치. 모든 모델의 roundtrip 테스트를 Phase 1에서 확보하면 후속 Phase에서 모델 변경으로 인한 연쇄 실패 방지.

**영향:** Phase 1의 작업량이 증가하지만, Phase 2~5에서 모델 관련 재작업 위험 제거.

### 3. TDD 실행 전략

**제시된 옵션:**
- A) Bottom-up: 모델 → Protocol → Fake → DI → 서비스 → CLI — 리서치 권장
- B) Outside-in: CLI 스켈레톤 → DI → Protocol → 모델 — 사용자 관점 우선

**사용자 결정:** A) Bottom-up

**근거:** 의존 체인을 따라 바닥부터 쌓으면 각 레이어가 이전 레이어의 테스트를 통과한 상태에서 구축됨. Red-Green-Refactor 사이클이 자연스럽게 적용됨.

**영향:** 구현 순서가 명확하게 고정됨. 계획 수립 시 이 순서를 따라 task를 배치.

### 4. Git 연동 방식

**제시된 옵션:**
- A) ★ 순수 subprocess — 의존성 최소, 비동기 네이티브, 프로세스 누수 없음 (리서치 권장)
- B) GitPython — Pythonic API, 편의성
- C) 하이브리드 — 읽기는 GitPython, 쓰기는 subprocess

**사용자 결정:** C) 하이브리드

**근거:** 사용자가 읽기 작업의 편의성(GitPython의 Pythonic API)과 쓰기 작업의 안전성(subprocess의 프로세스 격리)을 모두 원함.

**영향:** GitPython이 런타임 의존성에 추가됨. `Repo` 객체 생명주기 관리 규칙 필수. Git 어댑터가 두 가지 백엔드를 내부적으로 관리.

## Summary

4개 영역 모두 명확하게 결정됨. 미결정 사항 없음. CONTEXT.md에 모든 결정 반영 완료.

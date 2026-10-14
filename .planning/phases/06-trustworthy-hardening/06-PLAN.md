# Phase 06 Plan — Trustworthy Hardening

## 목표

기존 공개 계약을 가능한 한 보존하면서, 실제로 재현된 보안·운영·증거 신뢰 결함을 최소 변경으로
해소한다. 새 프레임워크를 만들지 않고 기존 모델·서비스·CLI 경계를 강화한다.

## 전역 제약

- 사용자 dirty worktree를 보존하고 기존 변경을 되돌리지 않는다.
- 외부 프로젝트 코드를 복사하지 않고 검증된 설계 원칙만 적용한다.
- 모든 행동 변경은 Red → Green → Refactor 순으로 검증한다.
- “파일 존재”는 mapping일 뿐 proof/compliance가 아니다.
- commit/push/deploy는 수행하지 않는다.

## Task 1 — 경로 신뢰 경계

- [x] 실패 테스트: `..`, 절대경로, Windows drive/UNC, symlink parent 탈출.
- [x] 단일 `security.repo_paths` 유틸리티로 portable 상대경로 정규화와 containment 검증.
- [x] `GenerationNode`, `GeneratedFile`, runtime materialization, case persistence에 적용.
- [x] ContextPackBuilder가 symlink 파일과 repo 외부 대상을 읽지 않게 한다.
- [x] build subprocess의 secret-bearing env를 제거하고 외부 symlink target 복사를 차단한다.

## Task 2 — 현재 모델 정책

- [x] 은퇴 모델을 사용하는 테스트가 실패하도록 최신 기본값 계약을 먼저 작성.
- [x] primary/light 모델 상수를 한 곳에 정의.
- [x] `DdalggakConfig`의 모델 설정이 graph node 서비스까지 전달되도록 DI 확장.
- [x] Claude 비용표와 README/.env 예시를 현재 지원 모델에 맞춘다.

## Task 3 — 정직한 assurance 상태

- [x] 빈 파일이 proof/compliance로 승격되지 않는 반증 테스트 추가.
- [x] capability 상태에 `mapped`를 도입하고 행동 보고서가 없으면 `proved` 금지.
- [x] 표준 상태를 `mapped/partial/gap`으로 변경.
- [x] evidence 경로도 containment 검사하고 오류 이유를 결과에 보존.
- [x] GSD 기준 저장소 이전과 비교 기준 신선도를 문서/benchmark 메타데이터에 반영.

## Task 4 — 정합성 및 최종 게이트

- [x] 매개변수 없는 collection type을 제거해 strict Pyright 통과.
- [x] 삭제된 문서 인벤토리의 참조 파손을 복구.
- [x] Requirements/Roadmap/State를 실제 검증 결과와 동기화.
- [x] focused tests → full non-Playwright suite → Ruff → Pyright → build → dependency audit.
- [x] 경로 탈출 반증을 다시 실행해 차단을 확인.
- [x] 설정 sandbox mode와 실제 runtime을 일치시키고 미구현 mode를 fail-fast 처리.

## 완료 조건

- 악성 생성 경로가 모델 검증과 write boundary 양쪽에서 거부된다.
- 기본 설치가 은퇴 모델을 호출하지 않는다.
- 빈 artifact만으로 superset/standard satisfaction을 주장할 수 없다.
- 전체 자동 회귀, strict typing, lint, package build가 통과한다.
- 실행하지 못한 실 API/브라우저 검증은 완료로 가장하지 않고 잔여 위험으로 기록한다.

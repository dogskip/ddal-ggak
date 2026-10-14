# 검증 가능한 변경 구현 계획

**Goal:** 승인된 기준으로 기존 React·TypeScript 변경을 모델 없이 검사하고, 제한 수정·내보내기·명시적 반영·중단 복구를 같은 자료 계약으로 제공한다.
**Architecture:** 기존 검사·판정·원본 반영 책임을 확장한다. 새 자료는 verified-change/1에 보관하고, 고정 기준·관찰 자료·실행 권한·원본 반영 권한을 구분한다. 새 DB·서버는 추가하지 않는다.
**Tech Stack:** Python 3.12, 현재 Typer·Pydantic·LangGraph·Playwright, JSON Schema 2020-12, 로컬 Docker 호환 실행기.
**Decisions settled:** 미해결 설계 질문 없음. 사용자 승인과 3심 확정 설계 34~36을 구현 입력으로 사용한다. 세부 구현이 설계와 충돌하면 시험·공식 근거로 판단하고 변경을 기록한다.
**Verification:** 아래 집중 시험, 전체 일반 시험, 엄격 타입 검사, Ruff, 실제 headless 브라우저, wheel 설치·구성 검사, 자료 무결성·중단·반복 시험을 단계별로 실행한다.

---

## 기준과 작업 위치

- 기준 커밋: `2bd47eea7fc2363e13576a5ca4563a0eaa3900df`.
- 분기: `feat/verified-change-runtime`.
- 작업 위치: `/Users/bjchoi/.codex/worktrees/b48f/ddalggak`.
- SDD 정본: `docs/design/34-verified-change-design.md`, `35-verified-change-storage.md`, `36-verified-change-verification.md`, `verified-change/contract.schema.json`.
- 원본 main은 변경하지 않는다. 이번 구현의 자동 배포·유료 모델 호출·실제 외부 계정 사용은 없다.
- 직전 기준 검사: 일반 1,611개 통과, 명시적 Chromium 경로의 브라우저 7개 통과, 기본 브라우저 탐색의 데모 1개 실패, 엄격 타입 오류 37개. 새 작업의 실행 결과와 구분한다.
- README 상단 비교 그림 수정은 별도 분기에서 완료했다. `ef2a788`을 main에 반영하고 실제 GitHub의 영문·한국어 및 두 화면 크기를 확인했다. 이 구현 분기의 완료·출시 근거와 구분한다.

## 검증 절차

각 동작 변경은 실패 시험 작성 → 의도한 실패 확인 → 최소 구현 → 집중 시험 → 관련 회귀 순서다. 초기 실패와 수정 후 결과는 `evidence/`에 보관한다. 시험을 통과하도록 승인 기준·허용 오차·필수 여부를 낮추지 않는다.

```text
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest <focused paths> -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q -m "not playwright" -p no:cacheprovider
.venv/bin/pyright src/
.venv/bin/ruff check src/ tests/ scripts/
.venv/bin/ruff format --check src/ tests/ scripts/
DDK_E2E=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -q -m playwright -p no:cacheprovider
uv build
.venv/bin/python scripts/check_wheel.py <built wheel>
```

실제 모델 인증은 시험 환경에서 제거한다. 실제 브라우저는 headless만 사용한다. 경로를 지정한 실행과 기본 탐색 실행을 구분한다. 격리 실행기 없음은 호스트 실행으로 대체하지 않고 명시적 불가 결과로 검증한다.

## D0: 기존 보호·복구와 정상 검사

상태: 공통 보호·타입·취소·관리된 원본 반영을 구현했다. 전체 일반 시험 2,025개, 별도 화면 시험 18개가 통과했다. 현재 환경의 검사 통과를 아래 단계 전체의 완료로 확대하지 않는다.

| 작업 | 담당·주요 파일 | 먼저 실패시킬 조건 | 완료 조건 |
|---|---|---|---|
| 공통 경로·응답 보호 | boundary_guards; repo_paths·secret_paths·file_blocks·code_generator·auto_fix_planner·tempdir·context_pack_builder | .git/.ddk·인증·역슬래시·symlink/hardlink, 잘린 수정 응답 | VCT-08·11·25의 실제 거부·원본 동일 |
| 기존 타입·브라우저·취소 | runtime_readiness; Chromium·preflight·demo·case_report·progress·subprocess 연결 | 중첩 asyncio.run, 취소 뒤 손자 작업, 출력 상한, 현재 타입 오류 | 기본 탐색 E2E와 정적 검사 통과; 소유 작업 정리 |
| 원본 반영·복구 | root; ArtifactApplier·CLI delivery·Git 복구 경계 | 삭제된 원본을 create로 오인, 계획 후 편집/mode 변경, 두 번째 쓰기 실패, 강제 덮어쓰기 | 전체 사전 확인·현재 상태 일치 시만 복구·unknown 보존; 강제 Git 초기화 없음 |

원본 반영은 먼저 전체 상태를 확인하고 사본·기록의 내구성을 확인한다. 파일 삭제·권한 확대·외부 변경 덮어쓰기를 제공하지 않는다. CLI의 위험한 기존 옵션은 명확한 거부와 내보내기 대안을 제공한다.

## D1: 자료 계약과 모델 없는 검사

상태: 계약·저장·원본 포착·모델 없는 조율과 공통 서비스를 구현했다. 설치한 wheel의 schema 조회와 CLI·MCP 연결을 확인했다. 실제 검사 연결은 명시적으로 승인한 trusted-local과 로컬 Docker 격리 경로다. 후속 구현과 실행 근거는 11·12번 문서 및 isolated-final 기록을 따른다.

contract_storage 담당은 `models/verified_change.py`, `services/verified_change_store.py`, `services/durable_files.py`, `security/file_access.py`와 집중 시험을 맡는다. root는 기존 자료 저장과 호출 경계를 연결한다.

- schema의 유형·format과 의미·참조·상태 규칙을 저장·조회 양쪽에 적용한다.
- JSON 중복 키·잘못된 UTF-8·NaN/Infinity·크기·깊이·외부 참조를 거부한다.
- 고정 case와 완료 run을 변경하지 않는다. pending과 완료를 구분하고 실제 자료를 검증한 뒤 manifest를 마지막에 공개한다.
- run_id/request_sha256의 동일 요청은 조회, 다른 요청은 충돌이다.
- owned 파일 조회·원자적 교체·동기화·배타 잠금은 공통 구현을 사용한다.
- API 키·이미지 없이 모델 없는 검사를 실행하고 기준·후보·환경·검사·최신 회차의 대응을 검증한다.

완료 조건: VCT-01·04~06·13·15·16·23·30과 새 자료 계약 시험, 설치한 wheel의 schema 사용을 확인한다.

## D2: 실제 동작·화면·실행 경계

상태: 격리 정책과 브라우저 연결, 앱·검사 작업 전송을 구현했다. 현재 macOS ARM64·OrbStack Linux 환경에서 실제 기본 검사, headless 동작·RGB·외부 요청 차단·취소·하위 실행 정리를 확인했다. 다른 장비·실행기와 실제 Vite·Next.js 전체 지원은 별도 조건이다. 상세 범위는 [후속 검토](12-ISOLATED-EXECUTION-REVIEW.md)를 따른다.

- RuntimeValidator의 공통 경계를 통해 고정 Flow를 실행한다. 한 Flow는 같은 context, 다른 Flow는 다른 context다.
- 이동·클릭·입력·기대 결과·화면 비교·오류·실패 요청을 독립 관찰 자료로 연결한다.
- RGB 성분 차이와 명시적 기준을 적용한다. 기준 자동 갱신·선택자 자동 교체·허용 오차 증가는 없다.
- 실제 URL 해석·origin과 redirect·추가 페이지·하위 요청을 확인한다. Service Worker는 차단한다.
- 로컬 격리 실행기 사전 확인·앱/검사 작업 분리·읽기 전용 기준·외부 네트워크 차단·Chromium 보호 설정을 강제한다.
- trusted-local은 명시적 CLI 사용자 선택에만 제공하며 MCP에서 사용할 수 없다.

완료 조건: VCT-02~04·09·20~22·28·29의 실제 headless 동작·실패·차단 자료. 실행기 없는 환경의 거부를 실제 격리 성공으로 계산하지 않는다.

## D3: 제한 수정·원본 반영·stdio MCP

상태: 요청 비용 예약·정산과 관리된 반영·명시적 복구, CLI 5개 명령과 stdio MCP 검사·조회를 구현했다. 실제 종료 후 복구, 저장 실패, 외부 편집 보존을 확인했다. 하나의 새 수정 요청에 재검사와 비용 예약을 연결하는 절차는 미완료다.

- 한 요청의 회차 안에서 수정·HTTP 요청·비용·시간 상한을 유지한다.
- SDK 자동 재시도를 끄고 실제 요청 전 최대 비용 예약을 내구성 있게 보존한다. 같은 사례의 요청은 한 소유 잠금으로 직렬화한다.
- 미정 비용은 예약 전액 유지·새 모델 호출 차단, 실제 예약 초과는 blocked와 관측값 보존이다.
- 같은 실패와 후보 해시의 반복·수정 횟수·출력 제한·취소·깊이 제한을 거부 시험에 포함한다.
- CLI verify/repair/export/apply/recover/status와 MCP verify/repair/status는 같은 구현을 호출한다.
- 원본 반영은 명시적 case/run/변경 해시와 ready·정리·자료·잠금·동시 편집 조건을 확인한다. 중단 시 같은 기록에서 현재 상태를 대조한다.

완료 조건: VCT-05·07·11·12·14·23~27의 실제 수정 모의 응답·파일 반영·중단·MCP 연결 시험. 모델 모의 응답과 실제 제공자 검증을 구분한다.

## D4: 제품 효과와 지원 확대

상태: 미실행. 실제 사용자 모집·외부 비교·유료 모델 실행은 이번 자동 작업에서 실행하지 않는다.

실제 React·TypeScript 저장소 3개 이상, 고정 과제·분리된 최종 자료·독립 평가·설정과 검토 비용·실패 포함·반복 사용으로 효과를 판단한다. 탐색 반복을 독립 표본으로 합산하지 않는다. 구현과 로컬 시험 완료를 제품 우위·100점·스타 수 보증으로 표시하지 않는다.

## 담당 경계와 통합

각 담당은 지정한 파일만 수정한다. 공통 API 변경은 root에 먼저 전달한다. 모든 구현은 같은 분리 작업 폴더에서 진행한다. 사용자가 승인한 commit/push는 root가 검증 후 기능별로 진행하며 main 병합과 분기 정리는 포함하지 않는다. 각 단계의 초기 실패·집중 통과·전체 통합 결과와 남은 조건을 별도 기록한다.

초기 작업 증거는 [확인 기록](08-CHECKPOINT.md), 현재 결과는 아래 기능 보강과 최종 실행 기록을 따른다. 설계 정합성 검사·구현 시험·실제 격리·제품 효과를 합산하지 않는다.

## 2026-10-14 기능 보강

사용자 재평가 요청에 따라 기존 미완료 연결을 우선 구현한다. Aider의 수정 후 검사·시험과 Continue의 파일 편집·여러 단계 작업이 이미 제공되므로 기능 수만으로 차별성을 주장하지 않는다. 기존 코드 도구의 변경을 모델 없이 검사하고 자료 검토·제한 반영까지 연결하는 기존 목표를 유지한다. 공식 근거: [Aider](https://aider.chat/docs/usage/lint-test.html), [Continue](https://docs.continue.dev/cli/quickstart).

| 작업 | 범위 | 상태 |
|---|---|---|
| 공통 사용자 서비스 | 사례 가져오기·검사·순수 조회·민감 자료를 기본 제외한 ZIP·관리된 반영·복구 | 구현·독립 재검토 완료 |
| 실제 검사 연결 | 고정 실행계획·명령·시험 보고·headless Flow·복사본 실행·정리 | trusted-local 및 로컬 Docker 실제 실행·변조·상한·미정 차단 확인 |
| CLI | 기존 명령을 유지하는 change 하위 명령 5개·종료 값·JSON 출력 | 실제 기본 서비스·evaluator·headless 확인 |
| MCP | 동일 서비스 검사·조회, 실제 stdio 협상·입력 오류·동일 요청·취소 | SDK 해석 전 원문 보호·조회 무변경·권한 거부 확인 |
| 3심·회귀 | 독립 2·3심 반례, 전체 일반·브라우저·타입·형식·설치 검사 | 필수 잔여 지적 없음, 최종 결과는 별도 기록 |

새 자동 수정과 외부 사용자의 반복 사용을 완료로 간주하지 않는다. 실제 격리는 현재 확인한 장비·실행기·고정 시험 앱 범위다. 현재 main에 공개한 범위와 이 분기의 구현을 구분한다.

현재 기능 판단은 [재평가](09-FUNCTIONAL-ASSESSMENT.md), 심사 범위는 [새 3심 기록](10-FUNCTIONAL-REVIEW.md)을 따른다. 최종 명령 결과와 소스 SHA는 `evidence/2026-10-14-functional-final.json`에 기록한다.

## 2026-10-14 실제 격리 후속 구현

기본 경로의 실제 작업 전송과 환경 대조를 추가했다. 명세와 수용 조건은 [후속 계획](11-ISOLATED-EXECUTION-PLAN.md), 반례와 검토 범위는 [후속 검토](12-ISOLATED-EXECUTION-REVIEW.md), 최신 실행 근거는 `evidence/2026-10-14-isolated-final.json`이다. 앞의 functional-final은 이전 소스의 기록으로 유지한다. 같은 담당자의 세 단계 검토를 독립 3심으로 표시하지 않는다. 다음 기능 우선순위는 새 수정 요청의 재검사·비용 예약·중단 복구 연결이다.

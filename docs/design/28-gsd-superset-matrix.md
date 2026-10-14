# GSD 상위호환 매트릭스

> **Purpose:** GSD 기능 family별 inherit/elevate/new 분류와 proof 상태를 추적  
> **Authority:** Tier 0 — 이 문서는 identity/strategy/governance 수준의 전략 문서로, 하위 Tier와 충돌 시 이 문서가 우선한다.  
> **Status:** active — claims are executable-gate controlled
> **Inputs:** 27-identity-positioning.md, 02-prd.md  
> **Outputs:** 27-identity-positioning.md (Claim Gate), 08-consistency-review.md  
> **Supersedes:** 없음 (신규)  
> **Stale Trigger:** GSD capability family 추가/삭제 또는 proof 상태 변경 시  

## 목적

본 문서는 `딸깍`이 GSD 기능을 어떻게 **계승(inherit)**, **고도화(elevate)**, **확장(extend)** 하는지 capability family 단위로 명시한다.
이 문서는 parity/uplift claim의 기준이며, 선언만으로 상위호환을 주장하지 못하게 만든다.

## 상태 정의

| 상태 | 의미 |
| --- | --- |
| `inherit-target` | GSD capability를 동일 수준 이상으로 포함해야 함 |
| `elevate-target` | 동일 capability를 더 강한 reliability / governance로 강화해야 함 |
| `new-target` | GSD에 없던 capability를 추가해야 함 |
| `proof-pending` | 문서상 정의됐지만 실행 evidence는 없음 |
| `partial` | 선언한 artifact 일부만 현재 저장소에서 확인됨 |
| `mapped` | 선언한 artifact가 모두 확인됨. 행동 증명이나 동등성 판정은 아님 |
| `proved` | commit-pinned 행동 검증 receipt가 있고 해당 검증이 현재 소스에 대해 신선함 |

## Capability Matrix

> **Executable SSoT:** 이 표의 권위 있는 형태는 `benchmarks/capability-matrix.json`이며,
> `현재 상태` 칼럼은 더 이상 손으로 적지 않는다 — `ddk proof`가 evidence를 디스크에서
> 실제 resolve해 `mapped` / `partial` / `proof-pending`을 **계산**한다.
> 아래 값은 2026-07-27 소스 기준 스냅샷이며, 최종 판정은 항상 현재 `ddk proof` 출력이다.

| Capability Family | GSD Baseline | 딸깍 목표 | 분류 | Proof Artifact (primary) | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| 프로젝트 초기화 / 워크스페이스 | init, project bootstrap | 동일 + case workspace / artifact schema | inherit-target | `workspace/manager.py` + init tests | 🟦 mapped |
| 요구사항 수집 / 로드맵 | roadmap, phase planning | 동일 + interview-driven requirements elicitation | elevate-target | `design/interviewer.py` + REQ model | 🟦 mapped |
| phase 실행 / 검증 | execution / verification | 동일 + closed-loop certify | elevate-target | `services/pipeline_runner.py` + release_gate | 🟦 mapped |
| 디버깅 / 회귀 수정 | debug workflows | 동일 + bounded deterministic auto-fix | elevate-target | `services/auto_fix_planner.py` + classifier | 🟦 mapped |
| 코드 리뷰 / 품질 게이트 | review/test culture | 동일 + architect-grade design quality gate | elevate-target | `services/scorecard_calculator.py` | 🟦 mapped |
| UI 설계/시각 흐름 | UI phase support | screenshot-driven intent + visual regression | new-target | `adapters/screenshot_diff_local.py` + SSIM tests | 🟦 mapped |
| 국제표준 설계문서 생성 | 부분/간접 | standards-aware design package | new-target | `design/generator.py` + templates | 🟦 mapped |
| standards mapping audit | 명시적 matrix 없음 | clause-to-artifact mapping | new-target | `services/compliance_auditor.py` + standards-catalog (`ddk audit`) | 🟦 mapped |
| runtime validation | strong workflow validation | sandboxed build/type/lint/runtime + console capture | elevate-target | `services/runtime_validator.py` + build runner | 🟦 mapped |
| rollback / reproducibility | 일부 recovery patterns | checkpoint, rollback SOP, LLM metadata | elevate-target | `services/rollback_controller.py` + LLMCallRecord | 🟦 mapped |
| multi-tool adapters | 풍부함 | canonical `ddk` / MCP 기반 통합 | inherit-target | `installer.py` + `server.py` (MCP) | 🟦 mapped |
| benchmark / superiority discipline | baseline 존재 | parity matrix + category-bound proof + calibration ops | elevate-target | `services/proof_ledger.py` + matrix JSON | 🟦 mapped |
| operator model / release authority | implicit | explicit human operator model | new-target | doc 32 + `services/operator_authority.py` | 🟦 mapped |
| security / privacy governance | security-conscious workflows | redaction, path policy, provider policy | new-target | `security/` + sandbox policy | 🟦 mapped |

> **머신 검증 요약 (2026-07-27):** 14개 family는 artifact 기준으로 모두 `mapped`지만
> behavior receipt가 없어 `proved=0`이다. 따라서 parity·superset·superiority claim은
> 모두 **DENIED**, maturity는 **P-0**이다. `ddk audit`도 `mapped/partial/gap`만 보고하며
> 표준 충족이나 인증을 판정하지 않는다.

## 비교 기준 provenance

- 활성 GSD 계보: `open-gsd/gsd-core`, branch `next`
- 조사 시점 커밋: `c07734216ff223649e43c14d448511c75f74695a` (2026-07-27 확인)
- `gsd-build/get-shit-done`은 보관 저장소이므로 신규 비교 기준으로 사용하지 않는다.
- commit-pinned corpus 실행과 비교 scorecard가 없으면 기준이 최신이어도 동등성은 미증명이다.

## 해석 규칙

1. **inherit-target** 는 최소 parity를 의미한다.
2. **elevate-target** 는 reliability, governance, evidence 중 하나 이상이 강화되어야 한다.
3. **new-target** 은 GSD에 없던 capability family를 의미한다.
4. row 하나만 green이어도 전체 상위호환을 주장할 수 없다.

## Claim Gate 규칙

### Parity Claim
아래가 모두 있을 때만 capability family 단위 parity를 말할 수 있다.
- 해당 row 존재
- 구현 artifact와 test mapping 존재
- 현재 소스 커밋에 묶인 행동 검증 receipt 존재
- 관련 requirement / ADR / evidence pack link 존재

### Superset Claim
아래가 모두 있을 때만 문서 수준 상위호환을 말할 수 있다.
- 핵심 capability family가 matrix에 누락 없이 존재
- `inherit-target` / `elevate-target` family가 모두 행동 증명됨
- `27-identity-positioning.md` 의 Claim Gate 통과

### Superiority Claim
아래가 모두 있을 때만 상대 우위를 말할 수 있다.
- capability family parity evidence
- benchmark / measured artifact
- calibrated threshold / baseline freshness

## 구현자용 사용법

- 새로운 기능을 추가할 때는 먼저 이 matrix에 family row를 추가한다.
- 구현이 끝나면 `proof artifact` 칼럼을 실제 파일/보고서로 채운다.
- claim은 matrix status가 `proved`이고 신선도 검사가 통과한 범위로만 제한한다.

## 결론

`딸깍`의 GSD 상위호환성은 slogan이 아니라 matrix여야 한다.
이 문서는 그 matrix의 권위 문서다.

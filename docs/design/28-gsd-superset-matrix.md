# GSD 상위호환 매트릭스

> **Purpose:** GSD 기능 family별 inherit/elevate/new 분류와 proof 상태를 추적  
> **Authority:** Tier 0 — 이 문서는 identity/strategy/governance 수준의 전략 문서로, 하위 Tier와 충돌 시 이 문서가 우선한다.  
> **Status:** proposed  
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
| `proved` | implementation/test/evidence link가 존재 |

## Capability Matrix

| Capability Family | GSD Baseline | 딸깍 목표 | 분류 | Proof Artifact | 현재 상태 |
| --- | --- | --- | --- | --- | --- |
| 프로젝트 초기화 / 워크스페이스 | init, project bootstrap | 동일 + case workspace / artifact schema | inherit-target | init tests, schema artifacts | proof-pending |
| 요구사항 수집 / 로드맵 | roadmap, phase planning | 동일 + interview-driven requirements elicitation | elevate-target | REQ artifacts, plan tests | proof-pending |
| phase 실행 / 검증 | execution / verification | 동일 + closed-loop certify | elevate-target | integration/e2e, release decision | proof-pending |
| 디버깅 / 회귀 수정 | debug workflows | 동일 + bounded deterministic auto-fix | elevate-target | failure taxonomy, fix loop tests | proof-pending |
| 코드 리뷰 / 품질 게이트 | review/test culture | 동일 + architect-grade design quality gate | elevate-target | quality gate reports | proof-pending |
| UI 설계/시각 흐름 | UI phase support | screenshot-driven intent + visual regression | new-target | visual artifacts, diff reports | proof-pending |
| 국제표준 설계문서 생성 | 부분/간접 | standards-compliant design package | new-target | design package + standards matrix | proof-pending |
| standards compliance audit | 명시적 matrix 없음 | clause-to-artifact mapping + audit gate | new-target | compliance matrix, audit report | proof-pending |
| runtime validation | strong workflow validation | sandboxed build/type/lint/runtime + console capture | elevate-target | runtime reports | proof-pending |
| rollback / reproducibility | 일부 recovery patterns | checkpoint, rollback SOP, LLM metadata | elevate-target | rollback reports, LLMCallRecord | proof-pending |
| multi-tool adapters | 풍부함 | 동일 + canonical `ddk` / MCP 기반 통합 | inherit-target | install adapter tests, MCP e2e | proof-pending |
| benchmark / superiority discipline | baseline 존재 | parity matrix + category-bound proof + calibration ops | elevate-target | benchmark artifacts | proof-pending |
| operator model / release authority | implicit | explicit human operator model | new-target | operator SOP, approval records | proof-pending |
| security / privacy governance | security-conscious workflows | data classification, redaction, retention, provider policy | new-target | governance report, security tests | proof-pending |

## 해석 규칙

1. **inherit-target** 는 최소 parity를 의미한다.
2. **elevate-target** 는 reliability, governance, evidence 중 하나 이상이 강화되어야 한다.
3. **new-target** 은 GSD에 없던 capability family를 의미한다.
4. row 하나만 green이어도 전체 상위호환을 주장할 수 없다.

## Claim Gate 규칙

### Parity Claim
아래가 모두 있을 때만 capability family 단위 parity를 말할 수 있다.
- 해당 row 존재
- 구현 artifact 또는 test link 존재
- 관련 requirement / ADR / evidence pack link 존재

### Superset Claim
아래가 모두 있을 때만 문서 수준 상위호환을 말할 수 있다.
- 핵심 capability family가 matrix에 누락 없이 존재
- `inherit-target` / `elevate-target` family가 proof plan에 연결됨
- `27-identity-positioning.md` 의 Claim Gate 통과

### Superiority Claim
아래가 모두 있을 때만 상대 우위를 말할 수 있다.
- capability family parity evidence
- benchmark / measured artifact
- calibrated threshold / baseline freshness

## 구현자용 사용법

- 새로운 기능을 추가할 때는 먼저 이 matrix에 family row를 추가한다.
- 구현이 끝나면 `proof artifact` 칼럼을 실제 파일/보고서로 채운다.
- claim은 matrix status가 `proved` 인 범위로만 제한한다.

## 결론

`딸깍`의 GSD 상위호환성은 slogan이 아니라 matrix여야 한다.
이 문서는 그 matrix의 권위 문서다.

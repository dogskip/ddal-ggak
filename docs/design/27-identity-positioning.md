# 제품 정체성 및 포지셔닝 SSoT

> **Purpose:** 딸깍의 제품 정체성(GSD++ + Design-to-Delivery OS)과 포지셔닝 규칙을 정의하는 SSoT  
> **Authority:** Tier 0 — 이 문서는 identity/strategy/governance 수준의 전략 문서로, 하위 Tier와 충돌 시 이 문서가 우선한다.  
> **Status:** proposed  
> **Inputs:** 02-prd.md  
> **Outputs:** 28-gsd-superset-matrix.md  
> **Supersedes:** 01-project-reconstruction.md, 36-proof-program.md  
> **Stale Trigger:** 제품 정체성 3축(Capability Lineage, System Identity, Proof Posture) 중 하나가 변경될 때  

## 목적

본 문서는 `딸깍`의 제품 정체성을 단일 진실 공급원(SSoT)으로 고정한다.
이후 모든 PRD, architecture, marketing, AI handoff 문서는 이 문서를 상위 입력으로 사용한다.

## SSoT 정체성 문장

> **딸깍은 GSD의 검증 중심 워크플로 계보를 지향하며, 설계문서 생성부터 구현·검증·자동수정·릴리즈 판단까지를 하나의 closed-loop로 연결하는 Design-to-Delivery 도구다.**

## 정체성의 세 축

| 축 | 정의 | 의미 |
| --- | --- | --- |
| Capability Lineage | **GSD++** | workflow breadth는 GSD를 계승·고도화한다 |
| System Identity | **Design-to-Delivery OS** | idea → requirements → design → build → validate → certify 를 하나의 체계로 묶는다 |
| Proof Posture | **Evidence-gated** | parity, superiority, release claim은 artifact와 gate를 통과해야 한다 |

## 왜 이런 정체성이 필요한가

1. `딸깍`을 단순 code generator로 정의하면 architect-grade 설계문서와 운영 거버넌스가 주변 기능으로 밀린다.
2. 반대로 generic OS로만 정의하면 visual/runtime/auto-fix loop의 강점이 흐려진다.
3. 따라서 `GSD++` 와 `Design-to-Delivery OS` 를 함께 써야 capability breadth와 system purpose가 동시에 드러난다.

## 제품이 해결하는 핵심 Job

### Job 1 — Architect-grade design synthesis
- 아이디어와 인터뷰만으로 국제표준에 맞는 설계문서 패키지를 만든다.

### Job 2 — Repo-aware implementation
- target repo conventions에 맞는 코드를 생성/정규화한다.

### Job 3 — Closed-loop delivery
- runtime/visual/autofix/certify를 끝까지 수행해 실제 통과 가능한 결과물로 수렴시킨다.

### Job 4 — Evidence-based governance
- 왜 통과했고 왜 실패했는지, 어떤 claim이 허용되는지 artifact와 gate로 보여준다.

## Capability Planes

| Plane | 내용 |
| --- | --- |
| Discover & Design Plane | interview, requirements, standards mapping, design package, AI handoff |
| Delivery & Verification Plane | ingest, analyze, generate, normalize, validate, visual-check, auto-fix, certify |
| Governance & Operations Plane | rollback, reproducibility, parity matrix, security/privacy, quality gate, proof program |

## Positioning Rules

### Allowed
- GSD 전체 기능을 포함·고도화하는 방향의 제품이라고 말할 수 있다.
- design-to-delivery 전체 수명주기를 관장하는 시스템이라고 말할 수 있다.
- architect-grade 설계문서와 closed-loop delivery를 함께 제공한다고 말할 수 있다.

### Not Allowed
- parity matrix와 evidence 없이 "GSD 전체 대체 완료"라고 말하면 안 된다.
- benchmark 없이 "GSD보다 우월하다"고 말하면 안 된다.
- operator model 없이 "완전 무인(one-click)" 시스템이라고 말하면 안 된다.

## Ambition Boundary vs Proof Boundary

### Ambition Boundary
- 제품이 최종적으로 포괄해야 하는 전체 범위다.
- breadth, standards, governance, enterprise readiness까지 포함한다.

### Proof Boundary
- 현재 릴리즈나 benchmark에서 실제로 증명 가능한 범위다.
- calibrated threshold, evidence pack, benchmark artifact, parity family evidence를 요구한다.

이 둘을 분리해야 포부는 넓게 유지하면서도 신뢰를 잃지 않는다.

## 메시징 원칙

1. **정체성은 넓게, 주장은 좁게**
2. **기능 수보다 proof와 reliability를 앞세운다**
3. **국제표준 준수는 clause mapping으로만 말한다**
4. **완벽한 자동화가 아니라 고신뢰 closed-loop automation을 말한다**

## 문서 적용 규칙

- `02-prd.md` 는 이 정체성 문장을 제품 정의에 반영해야 한다.
- `28-gsd-superset-matrix.md` 는 capability lineage를 구체화해야 한다.
- 상위 문서가 충돌할 경우 본 문서를 우선한다.

## Core Loops (from Project Reconstruction)

`딸깍`의 중심축은 다음 두 루프다.

### Architect Loop
`discover -> interview -> requirements -> standards map -> design package -> quality gate -> AI handoff`

### Delivery Loop
`ingest -> analyze -> plan -> generate -> normalize -> runtime validate -> visual regress -> auto-fix -> certify`

이 두 루프를 연결한 운영 체계가 `Design-to-Delivery OS` 이다.

## 핵심 가정(Assumptions)

1. `딸깍`의 1차 proof 대상은 **UI-centric web repo** 다.
2. architect-grade 문서는 코드 생성 이전의 품질을 결정한다.
3. GSD 기능 breadth와 closed-loop reliability는 동시에 추구하되, proof는 단계적으로 수행한다.
4. auto-fix는 bounded retries를 가져야 하며 실패 시 human escalation으로 끝나야 한다.
5. v1은 consumer one-click tool이 아니라 **operator-assisted developer tool** 이다.

## 주요 리스크(Risks)

| 리스크 | 설명 | 완화 방향 |
| --- | --- | --- |
| breadth vs proof tension | GSD++ ambition이 proof discipline을 압도할 수 있다 | capability와 claim gate 분리 |
| standards overclaim | 국제표준 준수 주장이 선언에 머물 수 있다 | clause mapping + quality gate 강제 |
| operator burden | manual review/approval 지점이 많아질 수 있다 | 역할과 승인권 정의 |
| governance sprawl | 문서가 많아지며 권위/최신성 혼란이 생길 수 있다 | status/stale 관리 |
| behavioral-proof gap | 구현·테스트 매핑은 있으나 GSD 동등성 행동 receipt가 없다 | commit-pinned corpus + freshness 검증 우선 |

## 검증 경로(Validation Path)

1. **Identity Proof** — `27` 과 `02` 가 같은 정체성을 가리키는지 검토
2. **Parity Proof** — `28` 의 capability families에 구현/evidence artifact 연결
3. **Standards Proof** — artifact별 표준 조항 실제 산출물 연결 검증
4. **P0 Delivery Proof** — React/Vite/TS repo에서 single screenshot + prompt → build/type/lint + visual diff + bounded auto-fix 증명
5. **Claim Proof** — release / parity / superiority claim은 아래 Claim Gate 기준 통과 시만 허용

## Claim Gate 및 Proof Program

### Claim 종류

| Claim Type | 설명 |
| --- | --- |
| Identity Claim | `딸깍은 GSD++ + Design-to-Delivery OS` 라는 정체성 선언 |
| Parity Claim | 특정 capability family에서 GSD parity/elevation 달성 |
| Superiority Claim | 특정 boundary에서 GSD 대비 우위 |
| Release Claim | 현재 build/package가 releasable 임 |
| Standards Claim | 특정 설계 패키지가 특정 표준을 충족함 |

### Gate 조건

1. **Identity Claim** — `27-identity-positioning.md` 존재 + `02-prd.md` 와 충돌 없음
2. **Parity Claim** — `28-gsd-superset-matrix.md` row + 구현/test mapping + 현재 커밋에 묶인 행동 검증 receipt + gate green
3. **Superiority Claim** — parity claim 선행 + `benchmarks/gsd-baseline.json` 존재 + threshold `calibrated` + comparative artifact 존재 + category boundary 명시
4. **Release Claim** — `07-verification-release.md` release blocker 없음 + `ReleaseDecision.status == ready` + required artifacts complete
5. **Standards Claim** — artifact mapping만으로는 불가; 해당 요구의 행동 검증과 권한 있는 검토 결과가 별도로 필요

### Proof Streams

| Stream | 필요한 증거 |
| --- | --- |
| Parity Proof | capability matrix + tests + artifact links |
| Design Quality Proof | architect-grade quality gate score |
| Runtime Proof | build/type/lint/runtime reports |
| Visual Proof | screenshot diff, threshold profile |
| Auto-fix Proof | fix history, bounded retries, rollback success |
| Security Proof | redaction, sandbox, policy checks |
| Reproducibility Proof | LLMCallRecord, context hash, replay comparability |
| Benchmark Proof | baseline freshness, comparative scorecard |

### Maturity Ladder

| Level | 의미 |
| --- | --- |
| `P-0` | artifact mapping만 있고 behavior proof receipt 없음 |
| `P-1` | 현재 커밋에 대한 일부 행동 receipt와 parity gate green |
| `P-2` | release-critical gate 및 핵심 parity family 행동 증명 |
| `P-3` | calibrated benchmark / standards / security governance 포함 |
| `P-4` | 반복 가능한 parity/superiority/release claim 체계 확립 |

Claim Gate는 더 이상 문서 규칙이 아니라 **실행 가능한 코드**다 (`ddk proof`,
`ddk.services.proof_ledger`, `benchmarks/capability-matrix.json`). evidence를
디스크에서 resolve해 mapping을 계산하고 claim을 허용/거부한다. 머신 검증 결과 현재는
artifact mapping만 있으므로 maturity **P-0**이며, parity·superset·superiority는 모두
**DENIED**다. 파일 존재는 행동 증명으로 승격되지 않는다.

### 금지 규칙

- baseline 없이 superiority claim 금지
- matrix 없이 superset claim 금지
- standards mapping 없이 compliance claim 금지
- operator model 없이 autonomous enterprise claim 금지
- rollback / security / reproducibility evidence 없이 release-ready claim 금지

## 결론

`딸깍`의 가장 정확한 정체성은 다음이다.

> **GSD++ 이면서, architect-grade Design-to-Delivery OS 이고, proof 없이는 과장하지 않는 시스템**.

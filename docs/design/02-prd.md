# PRD — 딸깍(Ddalggak)

## 1. 제품 한 줄 정의

`딸깍`은 **GSD 전체 기능을 포함·고도화한 `GSD++` capability envelope 위에,
architect-grade 국제표준 설계문서 생성부터 구현·검증·자동수정·인증까지를 하나의 CLI/MCP 체계로 수행하는 `Design-to-Delivery OS`** 다.

## 2. 제품 논지(Product Thesis)

`딸깍`의 제품 논지는 세 줄로 요약된다.

1. **GSD++**
   - 프로젝트 생성, 로드맵, phase 계획/실행/검증, 디버깅, 코드 리뷰, UI 작업, 테스트, 배포, multi-tool 사용성 등
     GSD가 가진 breadth를 포함·고도화한다.

2. **Architect-grade Design System**
   - 자연어/인터뷰로부터 요구사항을 수집하고,
     국제표준에 맞는 설계문서 패키지(SRS, PRD, Architecture, API, DB, Security, ADR, Test, Plan, AI Handoff)를 생성한다.

3. **Closed-loop Delivery Engine**
   - 생성된 결과를 `validate -> visual-check -> auto-fix -> certify` 루프로 끝까지 밀어 실제 통과 가능한 결과물로 수렴시킨다.

즉, `딸깍`은 **GSD의 breadth + architect-grade design synthesis + self-correcting delivery** 를 결합한 시스템이다.

## 3. 해결하려는 문제

### 문제 1. 생성기가 좋아도 제품이 아닐 수 있다

초안이 그럴듯해도 build/typecheck/lint/runtime/console/visual mismatch가 발생하면 결국 사람이 수습한다.

### 문제 2. 설계문서가 약하면 이후 구현 전체가 흔들린다

구조화되지 않은 아이디어, 표준 미준수 설계, 불명확한 acceptance criteria는 구현 실패와 재작업 비용으로 이어진다.

### 문제 3. 이미지 기반 생성은 본질적으로 확률적이다

semantic intent extraction은 확률적이므로 downstream validation이 없으면 precision ceiling을 넘지 못한다.

### 문제 4. 유지보수성은 repo alignment에서 갈린다

generated code가 repo conventions, file layout, tokens, primitives와 맞지 않으면 technical debt가 된다.

### 문제 5. GSD 상위호환 ambition과 실제 증명을 같은 문장으로 말하면 제품 신뢰가 무너진다

capability ambition은 넓게 가져갈 수 있지만, parity/superiority claim은 evidence boundary 안에서만 해야 한다.

## 4. 목표(Goals)

1. **GSD++ Capability Envelope**
   - GSD workflow breadth를 포함·고도화하고 없는 기능을 추가한다.

2. **Architect-grade Standards-compliant Design Package**
   - 요구사항 인터뷰부터 국제표준 기반 설계문서 패키지까지 생성한다.

3. **Closed Feedback Loop**
   - `generate -> normalize -> runtime validate -> visual regress -> auto-fix -> certify` 를 제품 기본 경로로 만든다.

4. **Operational Reliability**
   - build/type/lint/runtime/console/visual mismatch를 자동 수집하고 분류한다.

5. **Repo-aware Maintainability**
   - output이 target repo conventions와 design system을 따르도록 정규화한다.

6. **Bounded Self-healing**
   - auto-fix는 bounded retries 안에서만 수행하고 실패 시 evidence-rich escalation으로 끝낸다.

7. **Measured Proof Discipline**
   - parity, release, superiority claim은 matrix/benchmark/evidence artifact로만 허용한다.

8. **Truthful UX**
   - v1은 zero-friction consumer tool이 아니라 operator-assisted developer workflow임을 명시한다.

## 5. 비목표(Non-goals)

1. v1에서 multi-tenant control plane을 구현하지 않는다.
2. validation 없는 one-shot generation 성공을 제품 성공으로 간주하지 않는다.
3. bounded retry 없는 무한 auto-fix를 허용하지 않는다.
4. baseline artifact 없이 superiority claim을 하지 않는다.
5. "딸깍 한 번이면 끝"이라는 literal zero-setup UX를 v1에서 약속하지 않는다.
6. Python/TypeScript 외 언어 생태계 지원은 v2 이후로 미룬다.
7. parity matrix 없이 "GSD 전체 대체 완료"를 선언하지 않는다.

## 6. 핵심 사용자

### Persona A — Frontend/Product Engineer
- screenshot/reference를 repo에 맞는 코드로 빠르게 옮기고 싶다.

### Persona B — Solo Builder
- 생성 자체보다 최종 산출물이 실제로 통과하는지가 중요하다.

### Persona C — Reviewer/Lead
- 왜 통과했고 왜 실패했는지 evidence pack을 보고 싶다.

### Persona D — Architect/Consultant
- 요구사항부터 국제표준 설계문서까지 일관된 패키지를 빠르게 만들고 싶다.

## 7. Core Workflows

### Workflow A — Design Studio
1. `ddk design`
2. requirements elicitation interview
3. standards mapping
4. design package synthesis
5. design quality gate
6. AI handoff package emission

### Workflow B — Delivery Engine
1. `ddk ingest`
2. `ddk analyze`
3. `ddk generate`
4. `ddk normalize`
5. `ddk validate`
6. `ddk visual-check`
7. `ddk auto-fix`
8. `ddk certify`

## 8. P0 프로토타입 범위

정식 v1 전 반드시 먼저 구현할 최소 범위:

- 대상 repo: React/Vite/TypeScript single app
- 입력: one screenshot + one prompt + repo path
- 출력: single page or single component
- 검증: build + typecheck + lint + Chromium screenshot diff
- auto-fix: 최대 2회
- design side: 한 제품 슬라이스에 대한 standards-aware design package

P0가 green이 되기 전까지 broader expansion은 시작하지 않는다.

## 9. 기능 요구사항(Functional Requirements)

> **P0 구현 대상:** DDK-REQ-001~021 (Delivery Engine + CLI + Sandbox + LLM + Reproducibility + Preflight)  
> **P4 구현 대상:** DDK-REQ-022~024 (Design Studio)  
> **P5 구현 대상:** DDK-REQ-025~029 (Multi-tool Adapters + MCP)  
> AI 구현 시 반드시 P0 요구사항만 먼저 구현하고, P4/P5는 Phase 4/5에서 착수하라.

| ID | 기능 요구 | 설명 | 수용 기준(Acceptance) |
| --- | --- | --- | --- |
| `DDK-REQ-001` | Workspace Bootstrap | case workspace와 schema version을 초기화 | 재실행이 idempotent해야 한다 |
| `DDK-REQ-002` | Multimodal Intake | image, prompt, reference text를 구조화 입력으로 저장 | validated input artifact가 남아야 한다 |
| `DDK-REQ-003` | Repo Convention Scan | framework, naming, style, design system, file layout 추출 | reproducible repo profile이 생성돼야 한다 |
| `DDK-REQ-004` | Semantic Intent Model | image/prompt에서 layout/interaction/content intent를 추출 | confidence와 unresolved intent를 포함한 graph가 만들어져야 한다 |
| `DDK-REQ-005` | Design System Inference | tokens, spacing, typography, reusable primitives를 추론 | normalized design profile이 생성돼야 한다 |
| `DDK-REQ-006` | Generation Plan Graph | 작업을 ordered graph로 분해 | 각 node가 output, validate hook, repair hook을 가져야 한다 |
| `DDK-REQ-007` | Code Generation Engine | component/page code를 생성 | generated file map과 trace가 남아야 한다 |
| `DDK-REQ-008` | Post-generation Normalizer | naming/import/token/file placement drift를 줄인다 | repo convention diff가 감소해야 한다 |
| `DDK-REQ-009` | Sandboxed Runtime Validation Pipeline | build, typecheck, lint, runtime smoke를 격리 환경에서 실행 | structured runtime report와 sandbox metadata가 저장돼야 한다 |
| `DDK-REQ-010` | Console & Runtime Error Capture | browser console, runtime exceptions, failed requests를 수집 | structured error artifacts와 correlation ID를 남겨야 한다 |
| `DDK-REQ-011` | Visual Regression Runner | reference와 generated screenshot을 비교 | diff score, mismatch regions, pass/fail가 산출돼야 한다 |
| `DDK-REQ-012` | Bounded Auto-fix Loop | failure class별 patch를 만들고 재검증 | retry budget 내에서만 반복하고 exhaustion 시 escalates 해야 한다 |
| `DDK-REQ-013` | Failure Taxonomy | build/type/runtime/visual/data-binding/async 실패를 분류 | each failure가 stable taxonomy ID를 가져야 한다 |
| `DDK-REQ-014` | Evidence Pack Builder | 각 stage의 artifact/log/report를 묶어 저장 | replay 가능한 evidence pack이 생성돼야 한다 |
| `DDK-REQ-015` | LangGraph State & Context Orchestration | explicit graph state와 budgeted context packs를 관리 | node transitions, context inputs, retry compaction policy가 추적돼야 한다 |
| `DDK-REQ-016` | Sandboxed Execution Policy | generated code execution의 허용 범위와 격리 규칙을 강제 | out-of-sandbox execution은 blocked 되어야 한다 |
| `DDK-REQ-017` | Comparative Benchmark & Scorecard | precision/maintainability/automation/scalability score를 산출 | same harness에서 baseline과 비교 가능한 artifact가 있어야 한다 |
| `DDK-REQ-018` | Release Decision / Perfection Gate | known critical/blocker/scorecard를 집계하여 판정 | `ready/blocked/manual-review` 와 blocker 목록이 생성돼야 한다 |
| `DDK-REQ-019` | Auto-fix Rollback & Checkpoint | auto-fix 시도 전 git checkpoint를 생성하고, 시도 실패/exhaustion 시 named checkpoint로 revert 가능하게 한다 | 각 fix attempt마다 checkpoint ref가 artifact에 남아야 하고, `ddk rollback` 으로 복원 가능해야 한다 |
| `DDK-REQ-020` | Reproducibility & LLM Call Metadata | 각 LLM 호출의 model, provider, temperature, seed, schema version을 artifact에 저장한다 | 동일 run을 재실행할 때 context pack은 동일하게 재구성 가능해야 하고, model/provider 변경은 추적돼야 한다 |
| `DDK-REQ-021` | Preflight Doctor & Guided Setup | 케이스 실행 전 환경 전제 조건(build tool, LLM key, Playwright, sandbox)을 검사하고, 실패 항목마다 remediation hint를 출력한다 | 모든 필수 의존성이 없을 때 명확한 오류와 fix 방법이 출력되어야 하고, preflight green 없이는 실행이 시작되지 않아야 한다 |
| `DDK-REQ-022` | [Phase 4] Design Document Generator — Requirements Elicitation | 자연어 아이디어 입력 + 인터뷰를 통해 구조화된 요구사항을 수집한다 | validated input artifact에서 REQ-XXX 형식의 요구사항 목록이 생성돼야 하고, 각 항목에 우선순위·수용 기준·추적 ID가 포함되어야 한다 |
| `DDK-REQ-023` | [Phase 4] Design Document Generator — Standard-Compliant Doc Synthesis | 수집된 요구사항으로부터 10개 설계 문서를 자동 생성한다 | SRS(IEEE 830/29148), PRD(PR-FAQ), Architecture(ISO 42010/C4), API(OpenAPI 3.x), DB Schema(ERD), Security(ISMS-P/OWASP), ADR, Test Strategy, Implementation Plan, AI Handoff 각각이 표준 형식을 충족해야 한다 |
| `DDK-REQ-024` | [Phase 4] Design Document Generator — Quality Gate & Consistency Check | 생성된 설계 패키지의 완전성·일관성·AI 구현 가능성을 자동 검증한다 | 모든 REQ-XXX가 테스트·아키텍처·Phase 계획과 추적 가능해야 하고, 품질 점수(0~100)와 보완 권고 목록이 출력돼야 한다 |
| `DDK-REQ-025` | [Phase 5] Multi-tool Adapter — Claude Code | `ddk install --adapter claude` 실행 시 `.claude/commands/ddk/` 아래 모든 커맨드 파일과 `.mcp.json`을 자동 생성한다 | 설치 후 Claude Code에서 `/project:ddk/design` 호출 시 딸깍 엔진이 실행되어야 한다 |
| `DDK-REQ-026` | [Phase 5] Multi-tool Adapter — GitHub Copilot | `ddk install --adapter copilot` 실행 시 `.github/skills/ddalggak-*/skill.md`와 `.github/agents/ddalggak-*.md`를 자동 생성한다 | Copilot에서 `/ddk:커맨드` 호출 시 딸깍 엔진이 실행되어야 한다 |
| `DDK-REQ-027` | [Phase 5] Multi-tool Adapter — Gemini CLI | `ddk install --adapter gemini` 실행 시 `.gemini/extensions/ddalggak/extension.json`을 자동 생성한다 | Gemini CLI에서 `@ddalggak ddk_design` 호출 시 딸깍 엔진이 실행되어야 한다 |
| `DDK-REQ-028` | [Phase 5] Multi-tool Adapter — OpenCode & Codex | `ddk install --adapter opencode|codex` 실행 시 각 도구 설정 파일을 자동 생성한다 | OpenCode에서 MCP tool call, Codex에서 직접 ddk 실행이 동작해야 한다 |
| `DDK-REQ-029` | [Phase 5] MCP Server | `ddk mcp` 실행 시 stdio/HTTP transport로 MCP server가 기동되고, 딸깍 핵심 도구 15개 이상을 MCP tool로 노출한다 | MCP inspector로 tool 목록 확인 가능, Claude Code의 `.mcp.json` 연결 후 tool-use 성공해야 한다 |

## 10. 현재 보수 점수와 목표

| 축 | 현재 보수 평가 | 목표 조건 |
| --- | --- | --- |
| Precision | 7.5 | intent graph + visual regression + repo alignment 증명 |
| Maintainability | 7.0 | convention alignment와 normalization 안정화 |
| Automation | 6.5 | generate -> validate -> auto-fix 루프 증명 |
| Scalability | 6.0 | broader stack / multi-page / API flow에서 별도 증명 |
| Composite | 6.8~7.2 | category-bound benchmark에서 8.5+ 또는 parity/uplift 조건 달성 |

## 11. Success Metrics

| ID | 지표 | 기준 |
| --- | --- | --- |
| `SM-01` | P0 prototype success | defined P0 slice green |
| `SM-02` | Runtime gate reliability | release-blocking runtime failures 0 |
| `SM-03` | Visual gate reliability | release-blocking visual mismatches 0 |
| `SM-04` | Auto-fix boundedness | exhausted loops must end in explicit escalation |
| `SM-05` | Context efficiency | retry compaction works within budget |
| `SM-06` | Benchmarkability | `benchmarks/gsd-baseline.json` + current scorecard artifact both exist |
| `SM-07` | Truthful superiority | GSD 대비 claim은 measured proof boundary 안에서만 한다 |
| `SM-08` | Rollback safety | auto-fix exhaustion or manual-review 시 checkpoint revert가 성공해야 한다 |
| `SM-09` | Reproducibility | 동일 case를 재실행했을 때 context pack이 동일하게 재구성 가능해야 한다 |
| `SM-10` | Preflight completeness | 필수 의존성 누락 시 100% 명시적 오류 + remediation hint를 출력해야 한다 |
| `SM-11` | Design package quality | generated design package가 architect-grade quality gate를 통과해야 한다 |
| `SM-12` | Capability matrix coverage | parity/uplift matrix에 제품 핵심 capability family가 빠짐없이 매핑돼야 한다 |

## 12. GSD 대비 비교 전략

| 비교 축 | GSD 강점 | 딸깍 목표 |
| --- | --- | --- |
| General workflow breadth | 강함 | parity first, then architect-grade uplift |
| Design artifact synthesis | 부분적/간접적 | 국제표준 설계문서 생성 first-class 지원 |
| Verification | 강함 | runtime + visual + auto-fix + certify 결합 |
| Ops governance | 중간 | rollback, reproducibility, proof program, quality gate 강화 |
| Current product maturity | 이미 동작 중 | P0 이후에만 비교 가능 |

## 13. Truthful Launch Rule

다음을 구분한다.

### 13.1 Identity Claim
- `딸깍은 GSD++ + Design-to-Delivery OS` 라는 정체성 선언은 설계 수준에서 유지한다.

### 13.2 Parity Claim
다음이 있을 때만 특정 capability family에 대해 parity/uplift를 말한다.
- `28-gsd-superset-matrix.md` 의 대응 row
- 구현 또는 실행 artifact
- required test/evidence link

### 13.3 Superiority Claim
다음이 모두 충족되기 전까지 `딸깍`은 GSD를 넘는다고 말하지 않는다.
- `benchmarks/gsd-baseline.json` 존재
- P0 prototype green
- runtime validation pass
- visual regression pass
- bounded auto-fix evidence
- rollback safety evidence
- reproducibility artifact
- category-bound scorecard 또는 parity matrix evidence

즉 우월성은 **주장**이 아니라 **증거**여야 한다.

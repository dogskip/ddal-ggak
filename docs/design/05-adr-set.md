# ADR 세트

## ADR-001 — 제품을 Generic Workflow System이 아니라 Self-correcting Production Loop로 정의한다
- 상태: Proposed
- 결정: `딸깍`은 `generate -> validate -> fix -> certify` 루프를 제품 코어로 둔다.
- 결과: breadth보다 operational reliability가 중심 지표가 된다.

## ADR-002 — Python + Pydantic + LangGraph를 기본 스택으로 채택한다
- 상태: Proposed
- 결정: state models는 Pydantic v2, orchestration은 LangGraph로 설계한다.
- 결과: explicit state transition, validation, replayability가 향상된다.

## ADR-003 — Image + Prompt + Repo Context를 3중 입력 소스로 사용한다
- 상태: Proposed
- 결정: visual reference, textual intent, repo context를 함께 입력으로 받는다.
- 결과: image-only ambiguity와 repo mismatch를 줄인다.

## ADR-004 — Repo Convention Alignment를 별도 Normalization Stage로 분리한다
- 상태: Proposed
- 결정: generation 직후 normalize 단계를 넣는다.
- 결과: maintainability와 reviewer acceptance가 올라간다.

## ADR-005 — Runtime Validation을 Mandatory Gate로 둔다
- 상태: Proposed
- 결정: build, typecheck, lint, runtime smoke, console capture를 성공 판정 전에 수행한다.
- 결과: fake success를 줄인다.

## ADR-006 — Visual Regression을 UI-affecting 작업의 Mandatory Gate로 둔다
- 상태: Proposed
- 결정: UI 변경은 screenshot diff와 mismatch localization을 통과해야 한다.
- 결과: visual truth source가 생긴다.

## ADR-007 — Auto-fix Loop는 Bounded Retries로만 허용한다
- 상태: Proposed
- 결정: 기본 retry budget은 3이며 이후에는 escalation으로 끝낸다.
- 결과: 무한루프와 비용 폭발을 막는다.

## ADR-008 — Failure Taxonomy를 코어 도메인으로 둔다
- 상태: Proposed
- 결정: build/type/runtime/visual failure를 stable taxonomy ID로 분류한다.
- 결과: fix 전략과 benchmark가 측정 가능해진다.

## ADR-009 — Scorecard 기반 비교를 superiority claim 전에 요구한다
- 상태: Proposed
- 결정: scorecard와 evidence pack 없이는 superiority claim 금지.
- 결과: 마케팅성 주장보다 검증 가능한 진술만 남는다.

## ADR-010 — Structured Artifact를 Source of Truth로 사용한다
- 상태: Proposed
- 결정: intermediate/final state는 JSON artifact로 저장하고 Markdown은 설명용으로만 사용한다.
- 결과: replay, diff, contract testing이 쉬워진다.

## ADR-011 — Lowest Reliable Test Layer Policy를 유지한다
- 상태: Proposed
- 결정: deterministic logic은 unit, cross-layer는 integration, interfaces는 contract, critical loop만 E2E로 둔다.
- 결과: visual product라도 E2E explosion을 피한다.

## ADR-012 — Perfection을 Zero-known-critical-defect Policy로 정의한다
- 상태: Proposed
- 결정: known Sev0/Sev1, release-blocking visual/runtime mismatch, release-gating flaky가 0이어야 release 가능하다.
- 결과: 완벽이 운영 규칙이 된다.

## ADR-013 — Context Pack Builder를 코어 컴포넌트로 둔다
- 상태: Proposed
- 결정: 각 LLM 호출은 단계별 budgeted context pack을 받는다.
- 결과: retry loop의 중복 실패와 token 낭비를 줄인다.

## ADR-014 — Generated Code Execution은 Sandbox에서만 허용한다
- 상태: Proposed
- 결정: build/app boot/Playwright는 ephemeral worktree 또는 container 안에서만 수행한다.
- 결과: 보안성과 재현성이 올라간다.

## ADR-015 — Superiority Claims는 Measured GSD Baseline 이후에만 허용한다
- 상태: Proposed
- 결정: `benchmarks/gsd-baseline.json` 이 동일 harness에서 측정되기 전까지 superiority claim 금지.
- 결과: 비교의 정직성이 유지된다.

## ADR-016 — Auto-fix 시도 전 Git Checkpoint를 생성한다
- 상태: Proposed
- 결정: 각 auto-fix attempt 시작 전에 named checkpoint ref를 생성하고, exhaustion/manual-review 시 revert를 제공한다.
- 배경: evidence pack은 이력이지 복구 도구가 아니다. rollback 없는 auto-fix는 파일 상태를 되돌릴 수 없어 human recovery 비용이 크다.
- 결과: fix 실패 시 안전하게 pre-fix 상태로 돌아갈 수 있다.

## ADR-017 — 각 LLM 호출의 Metadata를 Artifact로 저장한다
- 상태: Proposed
- 결정: model, provider, temperature, seed, model_version, context_pack_hash를 `LLMCallRecord` 로 저장한다.
- 배경: LangGraph state는 graph 흐름을 저장하지 LLM 호출의 재현 조건을 저장하지 않는다.
- 결과: context 동일성 확인, model 변경 추적, run 재분석이 가능해진다.

## ADR-018 — 모든 실행 전 Preflight Doctor를 강제한다
- 상태: Proposed
- 결정: `ddk run` 은 preflight green 없이 시작하지 않는다. 실패 항목마다 remediation hint를 출력한다.
- 배경: Playwright 누락, LLM key 누락, Node.js 누락이 run 도중 발생하면 recovery 비용이 크다.
- 결과: setup 실패를 조기에 차단하고, operator가 빠르게 환경을 준비할 수 있다.

## ADR-019 — Model Complexity Routing으로 비용을 제어한다
- 상태: Proposed
- 결정: fix 복잡도에 따라 fast/cheap vs reasoning-capable 모델을 라우팅한다. 케이스당 cost cap을 설정 가능하게 한다.
- 배경: auto-fix 재시도 시 비용이 비선형으로 증가한다.
- 결과: 불필요한 고비용 호출을 줄이고, 예산 초과 시 graceful degradation이 가능해진다.

## ADR-020 — Primary LLM Provider는 Claude를 기준으로 하되 exact model metadata를 필수 저장한다
- 상태: Proposed
- 결정: Primary provider는 Anthropic Claude, fallback은 OpenAI로 두되 exact provider_model_id와 prompt_version을 artifact로 저장한다.
- 결과: provider strategy와 reproducibility가 연결된다.

## ADR-021 — P0 Sandbox는 Docker보다 Git Worktree를 우선 채택한다
- 상태: Proposed
- 결정: P0에서는 ephemeral git worktree를 sandbox 기본값으로 사용한다.
- 결과: 추가 설치 부담을 줄이고 rollback/checkpoint와 자연스럽게 통합한다.

## ADR-022 — Capability Ambition과 Proof Boundary를 별도로 문서화한다
- 상태: Proposed
- 결정: 제품 포부(`GSD++`)와 실제 claim 가능 범위(`proof boundary`)를 분리한다.
- 결과: 제품 정체성은 넓게 유지하면서도 과장된 superiority claim을 방지한다.

## ADR-023 — 국제표준 준수는 선언이 아니라 Explicit Compliance Matrix로 관리한다
- 상태: Proposed
- 결정: 설계 패키지는 standards clause와 artifact section을 직접 연결하는 matrix를 반드시 포함한다.
- 결과: "국제표준 준수"가 설명적 문구가 아니라 audit 가능한 산출물이 된다.

## ADR-024 — 문서 권위 체계와 Architect-grade Quality Gate를 운영 규칙으로 둔다
- 상태: Proposed
- 결정: 모든 핵심 설계문서는 authority, status, stale trigger를 가지며, package-level quality gate를 통과해야 한다.
- 결과: 문서가 늘어나도 최신성, 권위, 승인 상태를 통제할 수 있다.

## ADR-025 — Human Operator Model은 필수 설계 컴포넌트다
- 상태: Proposed
- 결정: ambiguity 해소, manual review, release authority, security sign-off는 명시된 역할 체계 위에서만 수행한다.
- 결과: "AI가 다 한다"는 모호한 표현 대신 실제 운영 책임이 명확해진다.

## ADR-026 — Security/Privacy Governance는 Prompt, Screenshot, Repo, Artifact 전체에 적용한다
- 상태: Proposed
- 결정: secrets, screenshots, repo contents, generated artifacts, benchmark data에 대한 분류/보존/전송 정책을 설계 문서에 포함한다.
- 결과: enterprise-grade 운영과 audit 가능성이 올라간다.

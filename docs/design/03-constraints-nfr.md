# 제약사항 및 비기능 요구사항

## 1. 설계 제약(Constraints)

| ID | 제약 | 설명 | 설계 영향 |
| --- | --- | --- | --- |
| `CON-01` | 저장소는 빈 상태다 | 구현 근거가 없다 | 설계에 검증 경로를 내장해야 한다 |
| `CON-02` | GSD는 동작하는 baseline이다 | 비교 기준은 이미 제품 수준이다 | 문서만으로 우월 주장 금지 |
| `CON-03` | image semantics는 probabilistic | 입력 1단계부터 불확실성이 있다 | visual/runtime verification이 필수다 |
| `CON-04` | repo alignment가 maintainability를 좌우한다 | 생성 품질보다 normalization이 중요하다 | repo scanner + normalizer를 core로 둔다 |
| `CON-05` | auto-fix는 무한루프가 되기 쉽다 | self-healing이 오히려 비용 폭탄이 될 수 있다 | bounded retries + escalation 필요 |
| `CON-06` | LLM context 관리가 공백이면 retry가 무의미하다 | state 저장만으로는 충분하지 않다 | explicit context pack builder가 필요하다 |
| `CON-07` | generated code 실행은 위험하다 | build/app boot/Playwright는 임의 코드 실행이다 | sandbox policy가 필수다 |
| `CON-08` | GSD baseline 수치가 없으면 gate가 공허하다 | 비교의 기준점이 없다 | baseline artifact가 선행조건이다 |
| `CON-09` | 제품명과 UX 마찰이 충돌한다 | v1은 zero-friction이 아니다 | truthful UX 선언 필요 |
| `CON-10` | API/domain/async는 P0 범위를 넘는다 | scalability 리스크가 크다 | v1 core와 vNext를 분리한다 |
| `CON-11` | rollback 없는 auto-fix는 파일 상태를 되돌릴 수 없다 | evidence는 이력이지 복구 도구가 아니다 | fix 시도 전 git checkpoint 생성이 필수다 |
| `CON-12` | LLM 출력은 seed/version 없이 재현 불가하다 | 동일 입력이어도 결과가 달라질 수 있다 | model/temperature/seed/provider version을 artifact에 저장해야 한다 |
| `CON-13` | setup 실패를 미리 잡지 않으면 실행 중간에 오류가 터진다 | Playwright 누락, key 누락이 run 도중 발생하면 recovery 비용이 크다 | preflight doctor가 실행 전에 전제 조건을 검사해야 한다 |
| `CON-14` | auto-fix 재시도 시 비용이 비선형으로 증가한다 | normalize + validate + visual + LLM fix가 매 시도마다 쌓인다 | model routing과 per-case cost cap이 필요하다 |

## 2. 비기능 요구사항(NFR)

| ID | NFR | 목표 | 검증 방법 |
| --- | --- | --- | --- |
| `NFR-01` | Precision | target visual/intent와 구현 결과의 일치율 향상 | visual diff + intent graph audit |
| `NFR-02` | Maintainability | generated code가 repo conventions와 호환 | normalization integration tests |
| `NFR-03` | Automation | human intervention 없이 닫힌 루프를 최대화 | auto-fix success rate + intervention rate |
| `NFR-04` | Runtime Correctness | build/type/lint/runtime/console failures 차단 | runtime validation pipeline |
| `NFR-05` | Visual Fidelity | screenshot diff를 통제 | visual regression suite |
| `NFR-06` | Bounded Self-healing | 무한 fix loop 방지 | retry controller tests |
| `NFR-07` | Context Efficiency | 각 LLM 호출이 예산 안에서 필요한 정보만 사용 | context pack tests |
| `NFR-08` | Execution Safety | generated code가 격리 환경에서만 실행 | sandbox integration tests |
| `NFR-09` | Observability | 각 단계의 결과/실패/수정이 추적 가능 | evidence pack completeness |
| `NFR-10` | Benchmarkability | 현재 점수와 개선 효과를 계량 가능 | scorecard suite |
| `NFR-11` | CI Practicality | visual/runtime가 들어와도 CI 운영 가능 | staged gate policy |
| `NFR-12` | Perfection Gate | known critical/blocker가 0일 때만 release | release decision audit |
| `NFR-13` | Rollback Safety | auto-fix 실패/exhaustion 시 파일 상태를 이전으로 복원 가능 | rollback integration tests |
| `NFR-14` | Reproducibility | 동일 case의 context pack을 재구성 가능하고 model call metadata가 artifact에 존재 | reproducibility unit + contract tests |
| `NFR-15` | Guided Setup | 필수 의존성 누락 시 명확한 오류와 fix 방법 안내 | preflight doctor tests |
| `NFR-16` | Cost Predictability | 케이스당 예상 비용이 사전에 추정 가능하고, 예산 초과 시 조기 중단 | cost estimator unit tests |

## NFR 정량 목표 보완표

아래는 기존 NFR 정의에 측정 가능한 목표값을 추가한 보완 정보다.

| NFR ID | NFR 명 | 목표값 | 측정 방법 |
|--------|--------|--------|-----------|
| NFR-01 | P0 단일 케이스 실행 시간 | 단순 케이스: ≤ 120초, 자동 수정 포함: ≤ 300초 | E2E 테스트 duration 측정 |
| NFR-02 | LLM 호출 비용 (케이스당) | P0 케이스당 ≤ $0.10 (Claude Sonnet 기준) | cost_tracker 집계 |
| NFR-03 | auto_fix 성공률 | P0 fixture 기준 ≥ 70% (1회 이내 수정 성공) | BM-001~005 벤치마크 |
| NFR-04 | 재현성 (동일 seed, 동일 context_pack_hash) | ≥ 95% 동일 결과 (best_effort mode) | 재현성 테스트 suite |
| NFR-05 | visual SSIM 임계값 | PASS: ≥ 0.95, FLAG: 0.85~0.95, FAIL: < 0.85 | 20-playwright-adapter.md 참조 |
| NFR-06 | preflight 실행 시간 | ≤ 30초 | `ddk preflight` 실행 시간 측정 |
| NFR-07 | context pack 빌드 시간 | ≤ 5초 (300 lines, 6 files 기준) | unit test 측정 |
| NFR-08 | rollback 성공률 | ≥ 99% (git ref 존재 시) | rollback 통합 테스트 |
| NFR-09 | CLI 응답 시간 (subcommand 시작) | ≤ 2초 (import overhead 포함) | startup time 벤치마크 |
| NFR-10 | 메모리 사용량 (P0 케이스) | ≤ 512MB (peak) | memory profiler 측정 |

## 3. 우선순위

1. `NFR-03 Automation`
2. `NFR-04 Runtime Correctness`
3. `NFR-05 Visual Fidelity`
4. `NFR-06 Bounded Self-healing`
5. `NFR-13 Rollback Safety`
6. `NFR-02 Maintainability`
7. `NFR-07 Context Efficiency`
8. `NFR-08 Execution Safety`
9. `NFR-15 Guided Setup`
10. `NFR-14 Reproducibility`
11. `NFR-10 Benchmarkability`
12. `NFR-16 Cost Predictability`
13. `NFR-01 Precision`
14. `NFR-11 CI Practicality`
15. `NFR-09 Observability`
16. `NFR-12 Perfection Gate`

## 4. 점수축(Score Axes)

| 축 | 현재 보수 평가 | 목표 |
| --- | --- | --- |
| Precision | 7.5 | 8.5+ |
| Maintainability | 7.0 | 8.5+ |
| Automation | 6.5 | 8.8+ |
| Scalability | 6.0 | v1 outside core, vNext target 8.0+ |
| Composite | 6.8~7.2 | specific category에서 8.5+ |

## 5. Perfection의 운영 정의

release 시 아래가 모두 0이어야 한다.

- known Sev0
- known Sev1
- release-blocking build failure
- release-blocking runtime/console failure
- release-blocking visual mismatch
- release-gating flaky tests
- retry budget exhaustion without escalation artifact
- unmapped release-gating requirements

## 6. 명시적 정책

### 6.1 Baseline Artifact Required
- `benchmarks/gsd-baseline.json` 이 없으면 superiority claim 금지
- benchmark gate는 baseline artifact가 존재할 때만 활성화

### 6.2 Runtime Validation 생략 금지
- build/typecheck/lint/runtime smoke/console capture 중 하나라도 빠지면 성공 판정 불가

### 6.3 Visual Regression 생략 금지
- UI-affecting 작업은 visual diff 없이는 성공 처리 금지

### 6.4 Bounded Retry Policy
- auto-fix는 최대 retry budget 내에서만 수행
- 예산 초과 시 `manual-review` 또는 `blocked`

### 6.5 Context Pack Policy
- 각 LLM 호출은 단계별 context pack을 사용
- retry 2/3에서는 failure summary를 압축해 토큰 예산을 넘지 않게 유지

### 6.6 Sandboxed Execution Only
- build/runtime/Playwright는 ephemeral worktree 또는 container에서만 수행
- network는 default deny
- writable path는 sandbox와 artifact dir만 허용

### 6.7 Timeout Defaults

| 대상 | 환경변수 | 기본값 | 최소값 | 근거 |
| --- | --- | --- | --- | --- |
| LLM API 호출 | `DDK_TIMEOUT_LLM_CALL_SECONDS` | 120s | 10s | Claude Sonnet 긴 코드 생성 시 60~90s 소요 |
| 프로젝트 빌드 | `DDK_TIMEOUT_BUILD_SECONDS` | 180s | 30s | Vite build + tsc 포함 |
| Playwright 캡처 | `DDK_TIMEOUT_PLAYWRIGHT_SECONDS` | 60s | 10s | 브라우저 기동 + 렌더링 + 스크린샷 |
| Sandbox 전체 | `DDK_TIMEOUT_SANDBOX_TOTAL_SECONDS` | 300s | 60s | build + runtime + visual 전체 예산 |
| Preflight doctor | (하드코딩) | 30s | — | 전제조건 검사는 빠르게 |

타임아웃 초과 시:
- LLM 호출: `LLMRetryableError(status_code=408)` → 재시도 정책 적용
- 빌드/Playwright: `SandboxTimeoutError` → 해당 단계 `failed`, auto-fix 가능
- Sandbox 전체: case를 `timeout` 상태로 전환, human escalation

### 6.8 Truthful UX
- v1은 operator-assisted workflow
- zero-setup, non-technical one-click UX는 비목표

## 7. 수용 불가 설계(Anti-goals)

- build만 되면 성공 처리하는 구조
- visual mismatch를 warning으로 축소하는 구조
- auto-fix를 무제한 재시도하는 구조
- repo convention drift를 formatter 문제로 축소하는 구조
- baseline artifact 없이 superiority gate를 켜는 구조
- sandbox 없이 generated code를 실행하는 구조

## 8. 결론

`딸깍`의 NFR은 breadth가 아니라 **closed-loop operational reliability** 를 최대화하는 방향으로 정렬되어야 한다.

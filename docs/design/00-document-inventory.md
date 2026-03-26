# 문서 인벤토리

## 목적

본 문서는 `딸깍` 설계 패키지의 근거 자료(evidence base), 문서군 구조, 최신 권위 상태를 정리한다.
이번 개정의 핵심은 제품 정체성을 **`GSD++ + Design-to-Delivery OS`** 로 고정하면서도,
실제 증명(proof)이 끝나기 전까지는 capability ambition과 superiority claim을 분리하는 것이다.

## 분석 대상 범위

| 범위 | 경로/출처 | 관찰 결과 |
| --- | --- | --- |
| 현재 저장소 | `/Users/bjchoi/SynologyDrive/projects/test/ddalggak` | 코드/CI/테스트 없이 설계문서만 존재하는 greenfield 상태 |
| 비교 기준 저장소 | `/Users/bjchoi/SynologyDrive/projects/github/get-shit-done` | GSD는 다수의 commands, workflows, tests, docs를 가진 성숙한 baseline |
| 핵심 실행 근거 | GSD의 `package.json`, workflow, tests | GSD는 이미 동작하는 workflow system 이다 |
| 사용자 의도 | 현재 대화 메시지 | `딸깍`은 GSD 기능 전체를 포함·고도화하고 architect-grade 국제표준 설계문서까지 생성하는 시스템이어야 한다 |

## 핵심 판단

1. 현재 `딸깍`은 구현물이 아니라 **설계 패키지** 다.
2. 제품 정체성은 단순 visual generator가 아니라 **GSD++ + Design-to-Delivery OS** 다.
3. 다만 비교 우위(superiority)는 여전히 **proof boundary** 안에서만 말해야 한다.
4. 따라서 문서군은 두 층을 동시에 가져야 한다.
   - **Capability ambition**: GSD 상위호환 + architect-grade design-to-delivery
   - **Proof discipline**: P0 slice, benchmark, evidence pack, calibrated gate

## 문서군 클러스터

| 클러스터 | 파일 범위 | 목적 |
| --- | --- | --- |
| 인벤토리 | `00` | 근거, 방향 수정, 비교 경계, 핵심 가정 |
| 제품/제약/설계 코어 | `02~09` | PRD, NFR, system design, ADR, verification, AI handoff |
| 구현 계약 | `10~26` | adapter, models, CLI, sandbox, prompt, benchmark, rollback 등 |
| 전략/거버넌스 | `27~28, 32~33` | identity, superset matrix, operator model, security/privacy |

## 권위도(Authority) 우선순위

1. **파일시스템 사실**
   - 현재 저장소에 실제 코드/CI/테스트가 있는지 여부.

2. **실행 가능한 설정/CI/테스트 코드**
   - 향후 생길 `package`, workflow, test artifacts.

3. **제품 정체성 SSoT 문서**
   - `27-identity-positioning.md`, `28-gsd-superset-matrix.md`

4. **요구사항/제약/아키텍처 문서**
   - `02-prd.md`, `03-constraints-nfr.md`, `04-system-design.md`, `05-adr-set.md`

5. **구현 계약 문서**
   - `10~26` 문서군

## 최신 설계 문서 목록 (Round 6 상위 전략 보강 후)

| 파일 | 제목 | 상태 |
|------|------|------|
| `00-document-inventory.md` | 문서 인벤토리 | 최신 |
| `02-prd.md` | PRD (DDK-REQ-001~029) | 최신 |
| `03-constraints-nfr.md` | 제약 및 NFR | 최신 |
| `04-system-design.md` | 시스템 설계 (6-Level Architecture) | 최신 |
| `05-adr-set.md` | ADR 세트 | 최신 |
| `06-tech-spec.md` | 기술 명세 (Phase 0~5) | 최신 |
| `07-verification-release.md` | 검증 및 릴리즈 | 최신 |
| `08-consistency-review.md` | 정합성 리뷰 | 최신 |
| `09-ai-handoff.md` | AI 구현 인계 패키지 | 최신 |
| `10-multi-tool-adapter.md` | 멀티툴 어댑터 설계 | 완전 |
| `11-llm-interface.md` | LLM 인터페이스 및 Provider 결정 | 완전 |
| `12-data-models.md` | Pydantic 모델 완전 스키마 | 완전 |
| `13-project-structure.md` | 프로젝트 디렉토리 구조 | 완전 |
| `14-cli-spec.md` | CLI 서브커맨드 완전 명세 | 완전 |
| `15-sandbox-design.md` | Sandbox 구현 명세 (WorktreeSandbox) | 완전 |
| `16-prompt-design.md` | 핵심 프롬프트 설계 | 완전 |
| `17-benchmark-baseline.md` | Benchmark Baseline 측정 명세 | 완전 |
| `18-reproducibility.md` | 재현성 정책 | 완전 |
| `19-langgraph-builder.md` | LangGraph StateGraph Builder 명세 | 완전 |
| `20-playwright-adapter.md` | Playwright 어댑터 및 RuntimeValidation 계약 | 완전 |
| `21-ci-workflow.md` | GitHub Actions CI Workflow 명세 | 완전 |
| `22-fixture-spec.md` | React/Vite/TS fixture repo 파일 명세 | 완전 |
| `23-auto-fix-rulebook.md` | Auto-fix deterministic rulebook | 완전 |
| `24-context-pack-determinism.md` | Context pack determinism 및 edge-case 명세 | 완전 |
| `25-rollback-recovery-sop.md` | Rollback failure recovery SOP | 완전 |
| `26-benchmark-calibration-ops.md` | Baseline/threshold 운영 상태 머신 | 완전 |
| `27-identity-positioning.md` | 제품 정체성·포지셔닝·Claim Gate SSoT (01, 36 흡수) | 최신 |
| `28-gsd-superset-matrix.md` | GSD 상위호환 매트릭스 | 신규/최신 |
| `32-human-operator-model.md` | Human-in-the-loop 운영 모델 | 신규/최신 |
| `33-security-privacy-governance.md` | Security/Privacy 거버넌스 | 신규/최신 |

## 이번 개정의 의미

### 이전 문서군의 강점
- runtime validation, visual gate, auto-fix, rollback, reproducibility, calibration ops가 이미 강했다.

### 이전 문서군의 부족한 축
- 제품 정체성 SSoT
- GSD 상위호환 증명 구조
- 국제표준 정합성의 명시적 매핑
- 문서 권위/승인/폐기 거버넌스
- human operator model
- 사업 패키징/GTM 서술
- ambition과 proof boundary의 분리

### 이번 개정으로 추가된 것
- `27`: 제품 정체성 SSoT + Claim Gate + Proof Program (01, 36 흡수)
- `28`: GSD 기능 포함·고도화·신규 추가를 분리한 capability matrix
- `32`: 사람 개입 지점과 역할 정의
- `33`: security/privacy governance

## 인벤토리 결론

- `딸깍`은 이제 문서 수준에서 **GSD++ + Design-to-Delivery OS** 로 정의된다.
- 그러나 저장소가 비어 있으므로, 이 정의는 여전히 **설계적 ambition** 이다.
- 제품 우위는 `28` 의 capability ambition, `27` 의 proof discipline, `07/17/26` 의 gate를 모두 충족할 때만 주장할 수 있다.
- 즉 현재 패키지는 **전략 + 아키텍처 + 운영 + 증명 체계** 를 포함한 고수준 설계문서군이며,
  남은 본질적 갭은 여전히 **구현과 실측 artifact** 다.

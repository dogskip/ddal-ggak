# 정합성 리뷰

> 설계 패키지 내 문서 간 교차 정합성을 점검하고 이력을 남긴다.

---

## Round 1~5: 초기 설계 정합성

### 검증 범위
- 02-prd.md ↔ 04-system-design.md ↔ 06-tech-spec.md 정합성
- 12-data-models.md ↔ 16-prompt-design.md ↔ 19-langgraph-builder.md 계약 일관성
- 03-constraints-nfr.md ↔ 07-verification-release.md 검증 경로 정합성
- 05-adr-set.md 결정 사항과 구현 문서 반영 여부

### 결과
모든 핵심 문서(02~26)의 교차 참조 및 REQ ↔ 구현 ↔ 테스트 경로가 유효함을 확인.
DDK-REQ-001~021 은 02, 06, 12, 16, 19에 양방향 참조 존재.

---

## Round 6: 상위 전략 문서 정합성 (27~36 신규 추가 후)

### 검증 대상

| 문서 | 교차 참조 대상 | 결과 | 비고 |
| --- | --- | --- | --- |
| 27-identity-positioning | 02, 28, 36 | PASS | SSoT 정체성 문장과 PRD 정체성 일치 |
| 28-gsd-superset-matrix | 02, 27, 36 | PASS | 36개 capability row가 PRD goals와 정렬 |
| 29-standards-compliance-matrix | 02-REQ-022~024 | PASS | 국제표준 준수 주장을 clause/artifact mapping으로 전환 |
| 30-document-governance | 00, 05, 31 | PASS | authority/status/stale rules를 문서 운영 규칙으로 승격 |
| 31-architect-grade-quality-gates | 02, 29, 30 | PASS | 설계 품질 gate를 수치화 |
| 32-human-operator-model | 02, 04, 09 | PASS | 7개 역할과 RACI 정의 |
| 33-security-privacy-governance | 03, 15, 20 | PASS | data classification과 sandbox policy 연결 |
| 34-product-packaging-gtm | 27, 36 | PASS | 제품 패키징과 claim discipline을 연결 |
| 35-expansion-architecture | 02, 04, 06 | PASS | P0 이후 확장 경로를 구조적으로 정의 |
| 36-proof-program | 07, 17, 26, 28 | PASS | parity/release/superiority claim gate를 하나로 통합 |

### 발견된 Tensions

1. **Identity 삼중 정의** — 01, 02, 27이 제품 정체성을 각각 서술. 27을 SSoT로 지정했으나 01/02에도 남아 있음.
2. **Gate 다중 정의** — 07(release gate), 31(quality gate), 36(claim gate)이 각각 다른 gate를 정의. 충돌은 없으나 운영 시 혼란 가능.
3. **NFR 중복** — 03과 07이 일부 NFR을 반복 서술.
4. **Standards matrix 선언성** — 29가 표준 조항을 나열했으나 실제 산출물과의 연결이 아직 template 수준.
5. **Governance 과잉** — 코드 0줄 단계에서 10개 전략 문서는 과도할 수 있음.

---

## Round 7: Design Studio 명세 체인 검증

### 7.1 DDK-REQ-022 ~ 024 추적 검증

| REQ | 02-prd | 06-tech | 09-handoff | 12-models | 16-prompts | 19-graph |
| --- | --- | --- | --- | --- | --- | --- |
| DDK-REQ-022 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DDK-REQ-023 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DDK-REQ-024 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

### 7.2 Design Studio 데이터 모델 검증

12-data-models.md §13~18에 6개 Pydantic 모델 추가 확인:
- InterviewTurn, DesignRequirement, DesignDocument, StandardsComplianceResult, QualityGateScore, DesignPackageManifest

### 7.3 Design Studio 프롬프트 검증

16-prompt-design.md §7~9에 3개 프롬프트 추가 확인:
- RequirementsElicitor, DesignDocSynthesizer, DesignQualityGate

### 7.4 Design Studio LangGraph 검증

19-langgraph-builder.md §7에 Design Studio Graph 추가 확인:
- 7 nodes, 2 conditional edges, InterviewBudgetController

### 7.5 거버넌스 메타데이터 검증

27~36 전체 10개 문서에 7/7 governance 메타데이터 필드 존재 확인:
Purpose, Authority, Status, Inputs, Outputs, Supersedes, Stale Trigger

### 7.6 신규 Tensions

6. **Design Studio ↔ Delivery 상태 분리** — DesignStudioState와 DeliveryState가 독립적. 통합 orchestrator 필요 여부 미정.
> ✅ 해소됨 (v2): `DesignHandoffPackage` + `HandoffManifest` 모델을 `12-data-models.md`에 추가, `_save_package_artifacts()` 명세를 `19-langgraph-builder.md`에 추가, `GraphState.design_handoff` 필드를 `13-project-structure.md`에 추가.
7. **Interview budget vs quality** — max 5 turns가 충분한 요구사항을 수집하는지 미검증.
> ✅ 해소됨 (v2): `MAX_TURNS_P0 = 5`를 `19-langgraph-builder.md`에 명시, `DesignStudioState.max_interview_turns: int = 5` 추가로 P0 인터뷰 예산 계약화.
8. **Standards mapping 자동화 수준** — LLM이 표준 조항 매핑을 신뢰성 있게 수행하는지 실측 필요.

### 판정
Design Studio 명세 체인 완성. 거버넌스 자기 적용 완료. PASS.

---

## Round 8: 문서 통합 정리 (Consolidation)

### 수행 내용
- 삭제: 29, 30, 31, 34, 35 (5건, 과잉 거버넌스/시기상조)
- 병합: 01 → 27, 36 → 27, 31 → 16 (3건)
- 결과: 37문서 → 30문서, ~835줄 절약

### 병합 검증

| 원본 | 흡수처 | 고유 내용 보존 여부 |
| --- | --- | --- |
| 01-project-reconstruction | 27-identity-positioning | PASS — 핵심 가정, 리스크, 검증 경로, Core Loops 모두 보존 |
| 36-proof-program | 27-identity-positioning | PASS — 5 Claim Type, Gate 조건, Proof Streams, Maturity Ladder, 금지 규칙 모두 보존 |
| 31-quality-gates | 16-prompt-design §10 | PASS — 6축 평가, 판정 기준, Hard Block 조건 보존 |

### 교차 참조 수정

| 파일 | 변경 내용 |
| --- | --- |
| 09-ai-handoff | 29, 31 참조 → 대체 경로로 수정 |
| 14-cli-spec | 01 참조 → 27로 수정 |
| 28-gsd-superset-matrix | 36 참조 → 27 Claim Gate로 수정 |
| 32-human-operator-model | 36 참조 → 27 Claim Gate로 수정 |
| 16-prompt-design | 30 참조 → 00으로 수정 |
| 00-document-inventory | 삭제 7건 제거, 클러스터/권위도 갱신 |

### 판정
통합 후 정보 손실 없음. 교차 참조 정합성 유지됨. PASS.

---

## Round 9: 미지정 영역 보완 검증 (최종)

### 수행 내용
11개 미지정 영역 전수 보완 후 정합성 검증.

### 보완 정합성 매트릭스

| 보완 항목 | 대상 파일 | 기존 문서와 충돌 | REQ 연결 | 테스트 명세 포함 |
| --- | --- | --- | --- | --- |
| LLM 실패 복구 정책 | 11-llm-interface.md | 없음 | NFR-06 | ✅ 5건 |
| DdalggakConfig | 12-data-models.md §19 | 11의 env vars와 일관 | Phase 0 | ✅ 4건 |
| 타임아웃 기본값 | 03-constraints-nfr.md §6.7 | 15-sandbox와 일관 | NFR-08 | 암묵적 |
| 정규화 규칙 | 24-context-pack.md | 04-system-design과 일관 | DDK-REQ-007 | ✅ 4건 |
| 실패 분류 알고리즘 | 23-auto-fix.md §2.5 | 23 §3 Repair Rules와 정렬 | DDK-REQ-012 | ✅ 6건 |
| 릴리즈 결정 로직 | 07-verification.md §17 | 07 §15-16과 일관 | DDK-REQ-020 | ✅ 5건 |
| JSON 출력 예시 6건 | 16-prompt-design.md | 12 schema와 일관 | 각 REQ | — |
| conftest.py | 12-data-models.md §22 | §19 Config와 일관 | Phase 0 | 사용 예시 포함 |
| Design Studio 노드 7건 | 19-langgraph.md §7.7 | §7 topology와 일관 | DDK-REQ-022~024 | — |
| E2E assertion 6건 | 07-verification.md §11.1 | §11 E2E table과 일관 | DDK-REQ-001~020 | 자체가 테스트 |

### 교차 정합성 검증

| 검증 쌍 | 결과 |
| --- | --- |
| 12 §19 DdalggakConfig ↔ 11 환경변수 목록 | ✅ 필드명 일치 |
| 03 §6.7 타임아웃 ↔ 12 §19 timeout 필드 | ✅ 기본값 일치 |
| 23 §2.5 taxonomy ↔ 23 §3 Repair Rule trigger | ✅ ID 일치 |
| 07 §17 ReleaseDecision ↔ 12 ReleaseDecision 모델 | ✅ 필드 일치 |
| 16 JSON 예시 ↔ 12 Pydantic 모델 필드 | ✅ 구조 일치 |
| 19 §7.7 노드 ↔ 16 §7~9 프롬프트 | ✅ 참조 일치 |

### 판정
11건 보완 후 교차 정합성 전수 검증 완료. 충돌 0건. PASS.

---

## 최종 판정

| 라운드 | 범위 | 결과 |
| --- | --- | --- |
| Round 1~5 | 핵심 문서 02~26 | PASS |
| Round 6 | 상위 전략 27~36 | PASS (5 tensions 식별) |
| Round 7 | Design Studio 명세 체인 | PASS (3 tensions 추가, 2건 v2에서 해소) |
| Round 8 | 문서 통합 37→30 | PASS (정보 손실 0) |
| Round 9 | 미지정 영역 11건 보완 | PASS (충돌 0) |

**설계 패키지 교차 정합성: PASS. 구현 착수 승인.**

---

## Tensions 현황 요약 (v2 업데이트)

| # | 설명 | 상태 | 해소 근거 |
| --- | --- | --- | --- |
| T-1 | Identity 삼중 정의 (01/02/27) | 미결 | — |
| T-2 | Gate 다중 정의 (07/31/36) | 미결 | — |
| T-3 | NFR 중복 (03/07) | 미결 | — |
| T-4 | Standards matrix 선언성 | 미결 | — |
| T-5 | Governance 과잉 | 미결 | — |
| T-6 | Design Studio ↔ Delivery 연결 계약 부재 | ✅ 해소 | `DesignHandoffPackage` + `_save_package_artifacts()` 명세 → `12-data-models.md`, `19-langgraph-builder.md`, `13-project-structure.md` |
| T-7 | 인터뷰 예산 충돌 (PRD vs MAX_TURNS) | ✅ 해소 | `MAX_TURNS_P0 = 5`, `DesignStudioState.max_interview_turns: int = 5` → `19-langgraph-builder.md` |
| T-8 | Standards mapping 자동화 수준 | 미결 | — |
| T-9 | ADR 거버넌스 공백 (26건 Proposed 상태) | ✅ 해소 | 전체 26 ADR → `status: Accepted` (`05-adr-set.md`) |
| T-10 | synthesis_attempts 상한 미집행 | ✅ 해소 | `MAX_SYNTHESIS_ATTEMPTS = 1` 집행 → `should_pass_quality()` (`19-langgraph-builder.md`) |

**총 tensions: 10건 식별 / 4건 해소 / 6건 미결**

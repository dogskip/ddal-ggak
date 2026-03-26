# Human-in-the-loop 운영 모델

> **Purpose:** 딸깍 운영의 인간 역할, RACI, 에스컬레이션 상태를 정의  
> **Authority:** Tier 0 — 이 문서는 identity/strategy/governance 수준의 전략 문서로, 하위 Tier와 충돌 시 이 문서가 우선한다.  
> **Status:** proposed  
> **Inputs:** 27-identity-positioning.md, 02-prd.md  
> **Outputs:** 27-identity-positioning.md (Claim Gate), 09-ai-handoff.md  
> **Supersedes:** 없음 (신규)  
> **Stale Trigger:** 역할 정의 변경, 자율성 수준 변경 시  

## 목적

본 문서는 `딸깍`에서 사람이 언제, 왜, 어떤 권한으로 개입하는지 정의한다.
`manual-review-required` 는 상태 이름일 뿐, 운영 모델이 아니므로 별도 문서가 필요하다.

## 역할(Role)

| 역할 | 책임 |
| --- | --- |
| Sponsor / Buyer | 제품 목표와 투자 판단 |
| Product Owner | scope, priority, acceptance 승인 |
| Architect | 설계 패키지 승인, 표준 정합성 판단 |
| Implementer | 코드/문서 생성 및 수정 |
| Verifier / QA | test, runtime, visual, release evidence 검토 |
| Security Reviewer | data handling, provider, secret policy 검토 |
| Release Authority | 최종 release / certify 승인 |

## 운영 단계별 인간 개입 지점

| 단계 | 자동화 가능 범위 | 인간 개입 필요 조건 |
| --- | --- | --- |
| Requirements interview | 초기 초안 생성 | ambiguous requirement, conflicting goals |
| Design package synthesis | 초안 자동 생성 | standards `flag/block`, missing requirement mapping |
| Code generation | 기본 생성 | insufficient context, forbidden change scope |
| Auto-fix | deterministic patch | no matching rule, budget exhaustion, rollback failure |
| Certify / release | artifact aggregation | release blocker, claim approval, security review |

## 승인권(Decision Rights)

- Product Owner: scope / priority / non-goals 승인
- Architect: design package `pass/flag/block` 승인
- Security Reviewer: security/privacy exception 승인
- Release Authority: `ready` 상태 최종 승인

## Escalation States

| 상태 | 의미 | 기본 담당자 |
| --- | --- | --- |
| `manual-review-required` | AI가 안전하게 계속할 수 없음 | Architect 또는 Implementer |
| `policy-review-required` | compliance / governance 판단 필요 | Architect + Security Reviewer |
| `release-review-required` | certify는 가능하지만 출고 승인 필요 | Release Authority |
| `blocked` | 자동 진행 금지 | 해당 책임자 전원 |

## Manual Review 최소 입력

manual review가 발생하면 아래 artifact가 있어야 한다.

- failure taxonomy
- latest validation report
- fix attempt history
- rollback report (있을 경우)
- recommended human actions

## RACI 개요

| 작업 | Responsible | Accountable | Consulted |
| --- | --- | --- | --- |
| requirements 확정 | Product Owner | Product Owner | Architect |
| design package 승인 | Architect | Architect | Product Owner |
| implementation run | Implementer | Architect | QA |
| release evidence 검토 | QA | Release Authority | Architect |
| security exception | Security Reviewer | Security Reviewer | Architect |

## Truthful UX 규칙

- v1은 완전 무인 시스템이 아니다.
- 사람 개입은 실패가 아니라 **신뢰성 경계** 다.
- operator model이 없으면 enterprise-grade claim은 금지한다.

## 결론

`딸깍`은 사람을 제거하는 시스템이 아니라,
**사람이 개입해야 하는 지점을 명시적으로 통제하는 시스템** 이다.

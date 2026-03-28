"""Design Studio — document generation prompt templates.

모든 문서 타입별 system prompt와 user message 템플릿을 여기서 관리한다.
각 템플릿은 (system_prompt, user_template) 쌍을 반환한다.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptTemplate:
    system: str
    user: str


# Shared system preamble for all document generation
_GENERATOR_BASE = """You are a world-class software architect and technical writer.
You produce precise, standards-compliant software design documents.

Rules:
- Write in Korean unless technical terms require English (code, commands, identifiers)
- Always output complete, ready-to-use documents — no placeholders like "[TODO]"
- Include concrete examples relevant to the project
- Follow international standards precisely (IEEE, ISO, OpenAPI, C4)
- Minimum document length: 800 words
- Use proper Markdown headings, tables, and code blocks
"""

TEMPLATES: dict[str, PromptTemplate] = {
    "00-interview-record": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate a structured interview record document.",
        user="""프로젝트: {project_name}

아이디어: {original_idea}

인터뷰 대화 내역:
{interview_transcript}

위 인터뷰를 바탕으로 **00-interview-record.md** 문서를 작성하라.

형식:
# 요구사항 수집 인터뷰 기록

## 기본 정보
- 프로젝트명, 날짜, 인터뷰 목적

## 인터뷰 전문
(대화 형식으로 재구성, 각 질문-답변 쌍)

## 도출된 핵심 요구사항 목록
- REQ-001: ...
- REQ-002: ...
(최소 10개)

## 우선순위 분류
| ID | 요구사항 | 우선순위 | 유형 |
|---|---|---|---|

## 미해결 질문
""",
    ),
    "01-srs": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate an IEEE 830 / TTA.KO-11.0166 compliant SRS document.",
        user="""프로젝트: {project_name}
인터뷰 요약: {interview_summary}

**01-srs.md — 소프트웨어 요구사항 명세 (IEEE 830 / TTA.KO-11.0166)** 를 작성하라.

필수 섹션:
1. 목적 및 범위
2. 전체 설명 (제품 관점, 사용자 특성, 제약 조건)
3. 기능 요구사항 (최소 15개 REQ-F-XXX, 각 설명 3줄 이상)
4. 비기능 요구사항 (성능, 보안, 가용성, 유지보수성 — ISO/IEC 25010 품질 모델 기반)
5. 외부 인터페이스 요구사항
6. 용어집 (Ubiquitous Language — 최소 20개 도메인 용어)
""",
    ),
    "02-prd": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate an Amazon PR-FAQ style PRD.",
        user="""프로젝트: {project_name}
요구사항 요약: {interview_summary}

**02-prd.md — 제품 요구사항 문서 (Amazon PR-FAQ 스타일)** 를 작성하라.

섹션:
1. Press Release (보도자료 형식 — 출시 가정 미래 시제로 작성)
2. FAQ — 고객 관점 (최소 10개 Q&A)
3. FAQ — 내부 이해관계자 관점 (최소 5개 Q&A)
4. 목표 지표 (KPI, OKR)
5. 성공 기준 (정량적 — DORA 메트릭 포함)
6. 범위 내/외 (In-Scope / Out-of-Scope)
7. 의존성 및 위험 요소
""",
    ),
    "03-architecture": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate a C4 Model + ISO/IEC 42010 architecture document.",
        user="""프로젝트: {project_name}
요구사항: {interview_summary}

**03-architecture.md — 시스템 아키텍처 (C4 Model + ISO/IEC 42010)** 를 작성하라.

섹션:
1. C4 Level 1 — Context Diagram (Mermaid C4Context)
2. C4 Level 2 — Container Diagram (Mermaid C4Container)
3. C4 Level 3 — Component Diagram (주요 컨테이너 1개, Mermaid)
4. 기술 스택 선택 및 근거
5. 배포 아키텍처 (클라우드/온프레미스)
6. 데이터 흐름 다이어그램
7. 확장성 전략
8. 장애 격리 전략

Mermaid 다이어그램 반드시 포함할 것.
""",
    ),
    "04-api-spec": PromptTemplate(
        system=(
            _GENERATOR_BASE
            + "\nGenerate an OpenAPI 3.0 compliant API specification in YAML format."
        ),
        user="""프로젝트: {project_name}
아키텍처 요약: {interview_summary}

**04-api-spec.yaml — API 명세 (OpenAPI 3.0)** 를 작성하라.

요구사항:
- YAML 형식
- openapi: "3.0.3"
- 모든 엔드포인트에 operationId, summary, description
- Request/Response 스키마 ($components/schemas 분리)
- 인증 (securitySchemes — JWT Bearer 기본)
- 에러 응답 (400, 401, 403, 404, 422, 500)
- 최소 10개 엔드포인트 (CRUD + 비즈니스 로직)
- 예시 데이터 (examples 섹션)
""",
    ),
    "05-database-schema": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate a comprehensive database design document.",
        user="""프로젝트: {project_name}
요구사항: {interview_summary}

**05-database-schema.md — 데이터베이스 설계** 를 작성하라.

섹션:
1. ERD (Mermaid erDiagram으로 전체 관계도)
2. 테이블 정의 (각 테이블: 목적, 컬럼 명세, 제약조건, 인덱스)
   - 최소 8개 테이블
   - 각 컬럼: 이름, 타입, NULL 여부, 기본값, 설명
3. 인덱스 전략 (읽기/쓰기 패턴 분석 기반)
4. 파티셔닝 전략 (필요 시)
5. 마이그레이션 전략
6. SQL DDL 스크립트 (CREATE TABLE 포함)
""",
    ),
    "06-security-design": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate an ISMS-P / OWASP Top 10 security design document.",
        user="""프로젝트: {project_name}
시스템 개요: {interview_summary}

**06-security-design.md — 보안 설계 (ISMS-P + OWASP Top 10)** 를 작성하라.

섹션:
1. 보안 목표 및 원칙 (기밀성/무결성/가용성)
2. 인증/인가 설계 (JWT + RBAC 상세)
3. OWASP Top 10 대응 계획 (각 항목별 구체적 대응)
4. 개인정보 처리 방침 (ISMS-P / GDPR 준수)
5. 암호화 전략 (전송 중/저장 시)
6. 보안 감사 로그 계획
7. 취약점 관리 프로세스
8. 인시던트 대응 절차
""",
    ),
    "07-adr-set": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate Architecture Decision Records (ADR) in MADR format.",
        user="""프로젝트: {project_name}
아키텍처 결정 배경: {interview_summary}

**07-adr-set.md — 아키텍처 결정 기록 세트 (MADR 형식)** 를 작성하라.

최소 8개 ADR을 작성하라. 각 ADR 형식:
---
## ADR-XXX: [결정 제목]
- **상태**: Accepted
- **날짜**: [날짜]
- **맥락**: 어떤 문제/상황
- **결정**: 무엇을 선택했나
- **근거**: 왜 이 선택인가
- **대안**: 고려한 대안들과 기각 이유
- **결과**: 이 결정의 영향
---

반드시 포함할 ADR 주제:
- 기술 스택 선택 (프레임워크, DB, 캐시)
- 인증 방식
- API 설계 방식
- 배포 전략
- 모니터링 전략
""",
    ),
    "08-test-strategy": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate a comprehensive TDD-based test strategy.",
        user="""프로젝트: {project_name}
시스템 개요: {interview_summary}

**08-test-strategy.md — 테스트 전략 (TDD 기반)** 를 작성하라.

섹션:
1. 테스트 피라미드 전략
2. 단위 테스트 (범위, 도구, 커버리지 목표 ≥80%)
3. 통합 테스트 (API, DB, 외부 서비스)
4. E2E 테스트 (사용자 시나리오 기반)
5. 성능 테스트 계획 (목표 TPS, 응답시간)
6. 보안 테스트 (SAST, DAST, 의존성 스캔)
7. TDD 워크플로우 (Red → Green → Refactor)
8. CI/CD 통합 방안
9. 테스트 데이터 전략
10. 핵심 테스트 케이스 목록 (최소 20개)
""",
    ),
    "09-implementation-plan": PromptTemplate(
        system=_GENERATOR_BASE + "\nGenerate a phased implementation plan with DORA metrics.",
        user="""프로젝트: {project_name}
전체 요구사항: {interview_summary}

**09-implementation-plan.md — 구현 계획 (DORA 메트릭 기반)** 를 작성하라.

섹션:
1. Phase 별 구현 계획 (최소 3 Phase)
   - 각 Phase: 목표, 산출물, 완료 기준
2. Phase 1 상세 태스크 분해 (최소 20개 태스크)
3. 기술 부채 관리 전략
4. DORA 메트릭 목표
   - Deployment Frequency, Lead Time for Changes, MTTR, Change Failure Rate
5. CI/CD 파이프라인 설계
6. 개발 환경 세팅 가이드
7. 팀 구성 제안 (역할, 책임)
""",
    ),
    "10-ai-handoff": PromptTemplate(
        system=(
            _GENERATOR_BASE
            + "\nGenerate an AI implementation handoff package — the most critical document."
        ),
        user="""프로젝트: {project_name}
전체 설계 요약: {interview_summary}

**10-ai-handoff.md — AI 구현 인계 패키지** 를 작성하라.

이 문서는 AI 에이전트 (Claude, GPT, Gemini 등)가 읽고
**즉시 구현에 착수**할 수 있도록 설계된 핵심 문서다.

섹션:
1. ## 프로젝트 원라이너
   (한 문장으로 무엇을 만드는지)

2. ## 즉시 시작하기
   ```bash
   # 환경 세팅부터 첫 실행까지 복사-붙여넣기 가능한 명령어
   ```

3. ## 구현 우선순위 (P0 → P3)
   | 우선순위 | 기능 | 의존성 | 예상 작업량 |
   
4. ## 핵심 도메인 모델
   (Python/TypeScript 코드로 주요 엔티티 명시)
   
5. ## API 엔드포인트 요약
   | Method | Path | 설명 | 인증 |

6. ## 데이터베이스 핵심 테이블
   (테이블명, 컬럼, 관계)

7. ## 환경 변수 목록
   ```env
   # 필수 환경 변수 전부 (예시값 포함)
   ```

8. ## 구현 체크리스트
   - [ ] 각 Phase별 완료 조건

9. ## 주의사항 및 제약사항
   (보안, 성능, 비즈니스 규칙 위반 금지 사항)

10. ## 참조 문서
    (다른 설계문서와의 관계)
""",
    ),
}

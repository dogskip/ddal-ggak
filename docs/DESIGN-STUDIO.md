# ddk design — 설계 스튜디오 완전 가이드

> **"만들고 싶은 것을 말하면, 세계 표준에 맞는 완전한 설계 문서 패키지를 만들어 준다."**
>
> AI 에이전트가 바로 구현에 착수할 수 있는 수준의 완성도.

---

## 목차

1. [이게 뭐야?](#1-이게-뭐야)
2. [어떤 문서가 나와?](#2-어떤-문서가-나와)
3. [어떤 표준을 따라?](#3-어떤-표준을-따라)
4. [사용 방법](#4-사용-방법)
5. [인터뷰 과정](#5-인터뷰-과정)
6. [생성 문서 상세](#6-생성-문서-상세)
7. [AI 구현 인계 패키지](#7-ai-구현-인계-패키지)
8. [품질 검증 기준](#8-품질-검증-기준)
9. [명령어 레퍼런스](#9-명령어-레퍼런스)

---

## 1. 이게 뭐야?

```
사용자 → "쇼핑몰 만들고 싶어"
         ↓
딸깍 인터뷰 (5~10분)
         ↓
10개 설계 문서 자동 생성
         ↓
AI 에이전트가 읽고 → 바로 구현 시작
```

`/ddk:design` (딸깍:설계) 는 아이디어 하나를 받아서, **구현 직전까지** 필요한 모든 설계 문서를 만든다.

만들어진 문서는:
- 국제 표준 (IEEE, ISO, OpenAPI) 형식을 따른다
- 업계 표준 (DDD, C4 Model, ADR, DORA) 구조를 따른다
- 한국 표준 (TTA, ISMS-P, 전자정부 프레임워크)에 맞는다
- AI 에이전트 (Claude, GPT, Gemini)가 읽고 바로 코드를 쓸 수 있다

---

## 2. 어떤 문서가 나와?

`ddk design new "쇼핑몰 만들고 싶어"` 실행 후 만들어지는 것:

```
design-package/
├── 00-interview-record.md        # 요구사항 수집 인터뷰 전문
├── 01-srs.md                     # 소프트웨어 요구사항 명세 (IEEE 830)
├── 02-prd.md                     # 제품 요구사항 문서 (Amazon PR-FAQ 스타일)
├── 03-architecture.md            # 시스템 아키텍처 (C4 Model)
├── 04-api-spec.yaml              # API 명세 (OpenAPI 3.0)
├── 05-database-schema.md         # 데이터베이스 설계 (ERD + 스키마)
├── 06-security-design.md         # 보안 설계 (ISMS-P 기반)
├── 07-adr-set.md                 # 아키텍처 결정 기록 (ADR)
├── 08-test-strategy.md           # 테스트 전략 (TDD 포함)
├── 09-implementation-plan.md     # 구현 계획 (Phase별)
└── 10-ai-handoff.md              # AI 구현 인계 패키지
```

---

## 3. 어떤 표준을 따라?

### 국제 표준

| 표준 | 적용 문서 | 내용 |
|---|---|---|
| **IEEE 830** | 01-srs.md | 소프트웨어 요구사항 명세 구조 |
| **ISO/IEC 25010** | 01-srs.md, 08-test-strategy.md | 소프트웨어 품질 모델 (기능성, 신뢰성, 사용성, 효율성, 유지보수성, 이식성) |
| **ISO/IEC 42010** | 03-architecture.md | 아키텍처 기술 표준 |
| **ISO/IEC 29148** | 01-srs.md | 요구사항 엔지니어링 프로세스 |
| **OpenAPI 3.0** | 04-api-spec.yaml | REST API 명세 표준 |
| **OWASP Top 10** | 06-security-design.md | 웹 보안 기준 |
| **UML 2.0** | 03-architecture.md | 아키텍처 다이어그램 표기법 |

### 업계 표준 (Industry Best Practice)

| 표준/패턴 | 적용 문서 | 내용 |
|---|---|---|
| **C4 Model** | 03-architecture.md | 4단계 아키텍처 시각화 (Context/Container/Component/Code) |
| **DDD** (Domain-Driven Design) | 01-srs.md, 03-architecture.md | Bounded Context, Ubiquitous Language, Aggregate |
| **ADR** (Architecture Decision Record) | 07-adr-set.md | 기술 결정 이유와 trade-off 기록 |
| **Amazon PR-FAQ** | 02-prd.md | 고객 관점 제품 요구사항 형식 |
| **Google Design Doc** | 전체 패키지 | 실용적 설계 문서 구조 |
| **DORA Metrics** | 09-implementation-plan.md | 배포 성능 기준 (Lead time, Deploy frequency, MTTR, Change failure rate) |
| **TDD** (Test-Driven Development) | 08-test-strategy.md | 테스트 우선 개발 전략 |

### 한국 표준

| 표준 | 적용 문서 | 내용 |
|---|---|---|
| **TTA.KO-11.0166** | 01-srs.md | 한국정보통신기술협회 소프트웨어 요구사항 명세 표준 |
| **TTA.KO-11.0032** | 03-architecture.md | 소프트웨어 아키텍처 기술 지침 |
| **ISMS-P** | 06-security-design.md | 정보보호 및 개인정보보호 관리체계 (과기정통부/KISA) |
| **전자정부 표준 프레임워크** | 03-architecture.md, 09-implementation-plan.md | 공공 SW 개발 표준 아키텍처 |
| **NIA 클라우드 보안** | 06-security-design.md | 국가정보화진흥원 클라우드 보안 기준 |
| **NIPA SW 개발 프로세스** | 09-implementation-plan.md | SW 개발 단계 및 산출물 기준 |

---

## 4. 사용 방법

### 기본 사용

```
# 아이디어만 넣기
/ddk:design  (딸깍:설계)  "쇼핑몰 만들고 싶어"

# 더 자세한 아이디어
/ddk:design  (딸깍:설계)  "배달 앱. 식당 목록 보고 주문하고 실시간 배달 추적"

# 파일로 아이디어 제공
/ddk:design  (딸깍:설계)  --idea idea.txt

# 특정 표준 집중
/ddk:design  (딸깍:설계)  "B2B SaaS CRM" --standard isms      # 보안 강화
/ddk:design  (딸깍:설계)  "전자정부 민원 시스템" --standard egov  # 전자정부 표준
/ddk:design  (딸깍:설계)  "핀테크 결제 플랫폼" --standard pci-dss  # 금융 보안
```

### 고급 옵션

```
# 인터뷰 없이 바로 생성 (자동 가정 적용)
/ddk:design  (딸깍:설계)  "쇼핑몰" --auto

# 특정 문서만 생성
/ddk:design  (딸깍:설계)  "쇼핑몰" --only api,database

# 기존 repo 기반으로 생성 (repo 분석 후 맞춤 설계)
/ddk:design  (딸깍:설계)  "결제 모듈 추가" --repo ./my-app

# 출력 폴더 지정
/ddk:design  (딸깍:설계)  "쇼핑몰" --output ./docs/design

# 설계 검토 (기존 설계 품질 점검)
/ddk:design-review  (딸깍:설계검증)  ./design-package/

# 설계 업데이트 (요구사항 변경 반영)
/ddk:design-update  (딸깍:설계수정)  --add "모바일 앱 지원 추가"

# 설계 내보내기
/ddk:design-export  (딸깍:설계내보내기)  --format pdf        # PDF
/ddk:design-export  (딸깍:설계내보내기)  --format notion     # Notion 페이지
/ddk:design-export  (딸깍:설계내보내기)  --format confluence # Confluence
```

---

## 5. 인터뷰 과정

`/ddk:design` (딸깍:설계)를 실행하면 딸깍이 5~10분 인터뷰를 진행한다.

### 인터뷰 단계 1: 핵심 이해 (2~3분)

```
딸깍: 어떤 문제를 해결하려고 하나요?
사용자: 동네 식당을 쉽게 찾고 예약하고 싶어

딸깍: 주요 사용자는 누구인가요?
사용자: 20-40대 직장인, 식당 사장님도 포함

딸깍: 가장 중요한 기능 3가지는?
사용자: 식당 검색/필터, 실시간 예약, 리뷰
```

### 인터뷰 단계 2: 기술 맥락 (2~3분)

```
딸깍: 웹/앱/둘 다?
사용자: 모바일 앱 우선, 웹도 나중에

딸깍: 예상 사용자 규모?
사용자: 처음엔 서울만, 나중에 전국

딸깍: 기존 비슷한 서비스가 있나요? 참고할 것?
사용자: 네이버 예약 같은 느낌, 더 간단하게
```

### 인터뷰 단계 3: 제약 & 우선순위 (1~2분)

```
딸깍: 개발 팀 규모?
사용자: 2명 (개발자 1, 디자이너 1)

딸깍: 출시 목표 시기?
사용자: 3개월 안에 MVP

딸깍: 보안/개인정보 특별 요건?
사용자: 결제 들어가면 PG사 연동 필요
```

### 결과

```
✅ 인터뷰 완료 — 23개 요구사항 추출
⏳ 10개 문서 생성 중...

  [1/10] 소프트웨어 요구사항 명세 (SRS)     ✅ 완료
  [2/10] 제품 요구사항 문서 (PRD)           ✅ 완료
  [3/10] 시스템 아키텍처 (C4)              ✅ 완료
  [4/10] API 명세 (OpenAPI 3.0)           ✅ 완료
  [5/10] 데이터베이스 설계 (ERD)           ✅ 완료
  [6/10] 보안 설계 (ISMS-P)              ✅ 완료
  [7/10] 아키텍처 결정 기록 (ADR)          ✅ 완료
  [8/10] 테스트 전략                      ✅ 완료
  [9/10] 구현 계획 (Phase별)             ✅ 완료
  [10/10] AI 구현 인계 패키지             ✅ 완료

📁 생성 위치: ./design-package/
📊 품질 점수: 92/100
⚠️  보완 권고: 성능 목표 수치 미확인 (--update로 추가 가능)
```

---

## 6. 생성 문서 상세

### 문서 01 — SRS (소프트웨어 요구사항 명세)

**표준:** IEEE 830, TTA.KO-11.0166, ISO/IEC 25010

**포함 내용:**

```markdown
# SRS — 식당 예약 플랫폼

## 1. 목적 및 범위
## 2. 이해관계자 (Stakeholders)
   - 주 사용자 (Primary Users)
   - 운영자 (Operators)
   - 외부 시스템 (External Systems)

## 3. 기능 요구사항 (IEEE 830 형식)
   | ID | 요구사항 | 우선순위 | 수용 기준 |
   | REQ-001 | 사용자는 위치 기반으로 식당을 검색할 수 있다 | P0 | 2km 이내 결과 < 2초 |
   | REQ-002 | 사용자는 날짜/시간/인원을 선택해 예약할 수 있다 | P0 | 예약 완료 후 SMS 발송 |

## 4. 비기능 요구사항 (ISO/IEC 25010 기반)
   - 성능 (Performance): API 응답 P95 < 500ms
   - 신뢰성 (Reliability): 가용성 99.9%
   - 보안 (Security): ISMS-P 준수
   - 사용성 (Usability): WCAG 2.1 AA
   - 확장성 (Scalability): 동시 사용자 10,000명

## 5. 제약사항
## 6. 가정 및 의존성
## 7. 외부 인터페이스 요구사항
## 8. 요구사항 추적 매트릭스 (RTM)
```

---

### 문서 02 — PRD (제품 요구사항 문서)

**표준:** Amazon PR-FAQ, Google Design Doc

**포함 내용:**

```markdown
# PRD — 식당 예약 플랫폼

## 1. 보도자료 형식 요약 (PR-FAQ 스타일)
   "서울 직장인, 이제 점심 예약을 앱 하나로 해결"

## 2. 자주 묻는 질문 (FAQ)
   Q: 기존 네이버 예약과 다른 점은?
   A: 소규모 식당 특화, 대기 알림, 단골 혜택

## 3. 사용자 페르소나
   - 페르소나 A: 김직장 (32세, 강남 IT 회사)
   - 페르소나 B: 박사장 (48세, 홍대 이탈리안 식당 운영)

## 4. 사용자 여정 (User Journey)
   검색 → 필터 → 식당 상세 → 예약 → 확인 → 방문 → 리뷰

## 5. 핵심 기능 우선순위 (MoSCoW)
   - Must: 검색, 예약, 알림
   - Should: 리뷰, 즐겨찾기
   - Could: AI 추천, 포인트
   - Won't: 배달 (v1 제외)

## 6. 성공 지표 (KPI)
   - MAU 10,000명 (3개월)
   - 예약 완료율 > 70%
   - 식당 만족도 > 4.0/5.0

## 7. 출시 기준 (Launch Criteria)
## 8. 위험 요소 및 완화 방안
```

---

### 문서 03 — 아키텍처 (C4 Model)

**표준:** ISO/IEC 42010, TTA.KO-11.0032, C4 Model

**포함 내용:**

```markdown
# 아키텍처 — 식당 예약 플랫폼

## 레벨 1: 시스템 컨텍스트 (Context Diagram)
   [사용자] → [식당 예약 앱] → [SMS 서비스 (Twilio)]
                              → [결제 PG (Stripe)]
                              → [지도 API (Kakao)]

## 레벨 2: 컨테이너 (Container Diagram)
   - Mobile App (React Native)
   - Web App (Next.js)
   - API Gateway (Kong)
   - Auth Service (JWT + Redis)
   - Restaurant Service (Node.js)
   - Reservation Service (Node.js)
   - Notification Service (Node.js + Queue)
   - Database (PostgreSQL + Redis)
   - Object Storage (S3)

## 레벨 3: 컴포넌트 (Component Diagram)
   [각 서비스별 주요 컴포넌트 상세]

## 도메인 모델 (DDD)
   - Bounded Context: Reservation, Restaurant, User, Review
   - Aggregate: Reservation(root), Restaurant(root)
   - Ubiquitous Language: 예약(Reservation), 슬롯(Slot), 취소(Cancellation)

## 데이터 흐름 (Data Flow)
## 배포 아키텍처 (AWS/GCP/Azure)
## 확장 전략 (Scale-out Plan)
```

---

### 문서 04 — API 명세 (OpenAPI 3.0)

**표준:** OpenAPI 3.0 (Swagger), REST 설계 원칙

```yaml
# api-spec.yaml
openapi: "3.0.3"
info:
  title: 식당 예약 플랫폼 API
  version: "1.0.0"
  description: RESTful API for restaurant reservation platform

paths:
  /restaurants:
    get:
      summary: 식당 목록 조회
      parameters:
        - name: lat
          in: query
          required: true
        - name: lng
          in: query
          required: true
        - name: radius
          in: query
          default: 2000
      responses:
        200:
          description: 식당 목록
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RestaurantList'

  /reservations:
    post:
      summary: 예약 생성
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateReservation'

components:
  schemas:
    Restaurant:
      type: object
      required: [id, name, address, lat, lng]
      properties:
        id: {type: string, format: uuid}
        name: {type: string, maxLength: 100}
        address: {type: string}
        lat: {type: number, format: float}
        lng: {type: number, format: float}
        rating: {type: number, minimum: 0, maximum: 5}
```

---

### 문서 05 — 데이터베이스 설계

**표준:** 정규화 원칙 (3NF), ERD 표기법 (IE Notation)

```markdown
# 데이터베이스 설계

## ERD (Entity-Relationship Diagram)
   [텍스트 ERD 또는 Mermaid 다이어그램]

## 테이블 정의

### users
| 컬럼 | 타입 | 제약 | 설명 |
|---|---|---|---|
| id | UUID | PK, NOT NULL | 사용자 ID |
| email | VARCHAR(255) | UNIQUE, NOT NULL | 이메일 |
| phone | VARCHAR(20) | NOT NULL | 전화번호 (예약 알림용) |
| created_at | TIMESTAMPTZ | NOT NULL, DEFAULT NOW() | 생성 일시 |

### restaurants
### reservations
### reviews

## 인덱스 전략
## 파티셔닝 전략
## 마이그레이션 전략
## 백업 및 복구 정책
```

---

### 문서 06 — 보안 설계

**표준:** ISMS-P, OWASP Top 10, NIA 클라우드 보안, PIPA (개인정보보호법)

```markdown
# 보안 설계

## ISMS-P 통제 항목 매핑
   - 2.1 정책의 유지관리: ✅ 보안 정책 문서화
   - 2.5 인증 및 권한관리: ✅ JWT + RBAC 구현
   - 2.6 접근통제: ✅ API Gateway 레벨 접근 제어

## 개인정보보호법 (PIPA) 준수
   - 수집 최소화: 예약에 필요한 정보만
   - 보존 기간: 예약 완료 후 3년
   - 파기 절차: 암호화 삭제

## 인증/인가 설계
   - 방식: JWT (Access 15분 + Refresh 7일)
   - RBAC: customer / restaurant_owner / admin

## API 보안
   - Rate Limiting: 100 req/min per IP
   - HTTPS 강제
   - CORS 정책
   - SQL Injection 방어 (Prepared Statements)
   - XSS 방어 (CSP Header)

## OWASP Top 10 대응
   | 위협 | 대응 방안 | 구현 위치 |
   |---|---|---|
   | A01 접근 제어 실패 | RBAC + API Gateway | Auth Service |
   | A02 암호화 실패 | TLS 1.3, AES-256 | 전체 |
   | A03 인젝션 | ORM 사용, 입력 검증 | API Layer |

## 보안 테스트 계획
## 취약점 대응 프로세스
```

---

### 문서 07 — ADR 집합 (Architecture Decision Records)

**표준:** Michael Nygard ADR 형식

```markdown
# ADR-001: 모바일 프레임워크 선택

상태: 수락됨 (Accepted)
날짜: 2025-01-15

## 결정
React Native를 모바일 앱 프레임워크로 선택한다.

## 맥락
iOS/Android 동시 지원 필요, 팀 인원 2명

## 옵션 비교
| | React Native | Flutter | 네이티브 |
|---|---|---|---|
| 코드 공유 | 90% | 95% | 0% |
| 팀 학습 비용 | 낮음 | 중간 | 높음 |
| 생태계 | 매우 큼 | 큼 | 큼 |
| 성능 | 좋음 | 매우 좋음 | 최고 |

## 결정 근거
팀이 React 경험 보유, JS 생태계 활용 가능, 커뮤니티 지원 충분

## 결과 (Consequences)
- 긍정: 개발 속도 향상, 코드베이스 단일화
- 부정: 네이티브 대비 성능 5~10% 손실

---
# ADR-002: 데이터베이스 선택
# ADR-003: API 아키텍처 (REST vs GraphQL)
# ADR-004: 인증 방식
# ADR-005: 배포 플랫폼
... (자동 생성)
```

---

### 문서 08 — 테스트 전략

**표준:** TDD, ISTQB, ISO/IEC 29119

```markdown
# 테스트 전략

## 테스트 피라미드 배분
   - 단위 테스트 (Unit): 70%
   - 통합 테스트 (Integration): 20%
   - E2E 테스트: 10%

## 기능별 TDD 적용 여부
| 기능 | TDD 모드 | 이유 |
|---|---|---|
| 예약 가능 슬롯 계산 | TDD Required | 순수 비즈니스 로직 |
| 결제 처리 | TDD Required | 금전 관련, 오류 비용 큼 |
| 식당 검색 API | TDD Preferred | 외부 의존성 있지만 로직 중요 |
| UI 컴포넌트 | TDD Optional | 시각적 요소, 테스트 후 작성 |

## 테스트 레이어별 범위
### 단위 테스트
- 예약 가능 여부 계산
- 금액 계산 (할인, 세금)
- 입력 유효성 검사
- 상태 전이 (예약 → 확정 → 취소)

### 통합 테스트
- 예약 생성 → DB 저장 → SMS 발송
- 결제 → 예약 확정 → 알림
- 식당 검색 → 위치 API 연동

### E2E 테스트 (핵심 6개만)
1. 회원가입 → 로그인
2. 식당 검색 → 예약 완료
3. 예약 취소 흐름
4. 식당 사장 예약 확인
5. 결제 실패 복구
6. 알림 수신 확인

## 릴리즈 게이트
- 단위 커버리지 > 80% (비즈니스 로직)
- E2E 6개 모두 통과
- 보안 취약점 0개 (Critical/High)
- 성능 테스트 P95 < 500ms
```

---

### 문서 09 — 구현 계획

**표준:** NIPA SW 개발 프로세스, Agile/Scrum, DORA Metrics

```markdown
# 구현 계획

## Phase 구조 (3개월 MVP 기준)

### Phase 0 — 기반 (1주)
- [ ] 프로젝트 초기화 (repo, CI/CD, 환경)
- [ ] 데이터베이스 스키마 마이그레이션
- [ ] 인증 서비스 (회원가입/로그인)
- 완료 기준: 로그인 후 토큰 발급 확인

### Phase 1 — 핵심 기능 (3주)
- [ ] 식당 등록/관리 (사장 앱)
- [ ] 식당 검색/필터 (위치 기반)
- [ ] 예약 생성/확인/취소
- 완료 기준: 예약 완료 후 SMS 수신 확인

### Phase 2 — 완성도 (2주)
- [ ] 결제 연동 (Stripe)
- [ ] 리뷰 시스템
- [ ] 알림 (SMS + 앱 푸시)
- 완료 기준: 실결제 성공 + 환불 테스트

### Phase 3 — 품질 & 배포 (2주)
- [ ] 성능 최적화
- [ ] 보안 검증
- [ ] 베타 테스트
- [ ] 프로덕션 배포
- 완료 기준: DORA 기준 배포 성공

## DORA 목표 (출시 후 3개월)
- Lead Time for Changes: < 1일
- Deployment Frequency: 주 3회 이상
- MTTR: < 1시간
- Change Failure Rate: < 5%
```

---

### 문서 10 — AI 구현 인계 패키지

**AI 에이전트가 이 문서 하나만 읽고 구현 시작할 수 있도록.**

```markdown
# AI 구현 인계 패키지

## 프로젝트 요약 (3줄)
식당 예약 플랫폼. React Native 앱 + Node.js API + PostgreSQL.
핵심: 위치 기반 식당 검색 + 실시간 예약 + SMS 알림.
MVP 범위: 서울, 3개월, 팀 2명.

## 즉시 시작할 것 (Phase 0)
1. `ddk phase plan 0` 실행
2. 다음 파일 먼저 작성:
   - `src/auth/jwt.service.ts` — JWT 발급/검증
   - `src/database/migrations/001_initial.sql` — 스키마

## 반드시 TDD로 작성할 것
- `src/reservation/slot-calculator.ts` — 예약 가능 슬롯 계산
- `src/reservation/reservation.service.ts` — 예약 생성/취소
- `src/payment/payment.service.ts` — 결제 처리

## 절대 하지 말 것
- 환경변수 하드코딩 (LLM_KEY, DB_URL 등)
- Phase 범위 초과 구현 (배달 기능은 v2)
- 테스트 없이 결제 코드 머지

## 컨텍스트 전달 방법
각 Phase 시작 전: 01-srs.md + 03-architecture.md + 해당 Phase 섹션만 전달
auto-fix 재시도 시: 이전 실패 요약 + 남은 시도 횟수 포함

## 검증 체크리스트
- [ ] 모든 API 엔드포인트 OpenAPI 명세와 일치하는가?
- [ ] DB 스키마가 05-database-schema.md와 일치하는가?
- [ ] 보안 요건 ISMS-P 항목 모두 구현됐는가?
- [ ] E2E 6개 시나리오 모두 통과하는가?
```

---

## 7. AI 구현 인계 패키지

`10-ai-handoff.md`는 설계 패키지의 핵심 출력이다.

AI 에이전트가 읽었을 때 즉시 구현을 시작할 수 있어야 한다. 기준:

| 항목 | 기준 |
|---|---|
| 모호성 (Ambiguity) | 해석 여지가 없는 명확한 기술 선택 |
| 완전성 (Completeness) | 모든 REQ-XXX에 구현 가이드 있음 |
| 순서 (Order) | Phase 0부터 순서대로 구현 가능 |
| 검증 가능성 | 각 Phase 완료 조건이 테스트로 표현됨 |
| 안전성 | 하지 말아야 할 것 명시 |

---

## 8. 품질 검증 기준

설계 패키지 생성 후 자동으로 검증한다.

```
ddk design review ./design-package/

검증 항목:
✅ 모든 REQ-XXX가 적어도 1개의 테스트와 매핑됨
✅ API 명세의 모든 엔드포인트가 SRS와 추적 가능
✅ ADR에서 근거 없는 기술 선택 없음
✅ 보안 OWASP Top 10 모두 대응됨
✅ Phase 계획이 REQ 우선순위와 일치
⚠️ 성능 목표 수치 미정 (권고: NFR-003에 구체적 수치 추가)

품질 점수: 92/100
```

### 완전성 체크리스트

| 항목 | 기준 | 자동 확인 |
|---|---|---|
| 요구사항 완전성 | 모든 REQ에 수용 기준 있음 | ✅ |
| 추적 가능성 | REQ → 아키텍처 → API → 테스트 연결됨 | ✅ |
| 보안 완전성 | ISMS-P 필수 항목 모두 포함 | ✅ |
| 테스트 커버리지 | 모든 비즈니스 규칙에 테스트 전략 있음 | ✅ |
| AI 구현 가능성 | Phase 0부터 순서대로 구현 가능 | ✅ |
| 표준 준수 | 명시된 표준 형식 충족 | ✅ |

---

## 9. 명령어 레퍼런스

| 명령 (슬래시커맨드) | 한국어 표시 | 설명 |
|---|---|---|
| `/ddk:design` | 딸깍:설계 | 새 설계 패키지 생성 (인터뷰 + 문서 생성) |
| `/ddk:design` `--auto` | 딸깍:설계 | 인터뷰 없이 자동 가정으로 생성 |
| `/ddk:design` `--repo .` | 딸깍:설계 | 기존 repo 분석 기반 설계 |
| `/ddk:design` `--standard isms` | 딸깍:설계 | ISMS-P 집중 보안 설계 |
| `/ddk:design` `--standard egov` | 딸깍:설계 | 전자정부 표준 프레임워크 적용 |
| `/ddk:design-update` | 딸깍:설계수정 | 기존 설계에 요구사항 추가 |
| `/ddk:design-review` | 딸깍:설계검증 | 설계 품질 자동 검증 |
| `/ddk:design-export` `--format pdf` | 딸깍:설계내보내기 | PDF 내보내기 |
| `/ddk:design-export` `--format notion` | 딸깍:설계내보내기 | Notion 내보내기 |
| `/ddk:design-export` `--format confluence` | 딸깍:설계내보내기 | Confluence 내보내기 |

---

## 요약

| | GSD | 딸깍 `ddk design` |
|---|---|---|
| 설계 문서 생성 | ❌ (없음) | ✅ 10개 자동 생성 |
| 국제 표준 (IEEE/ISO) | ❌ | ✅ IEEE 830, ISO 42010 등 |
| 업계 표준 (DDD/C4/ADR) | ❌ | ✅ 전부 포함 |
| 한국 표준 (TTA/ISMS-P) | ❌ | ✅ 전부 포함 |
| API 명세 (OpenAPI 3.0) | ❌ | ✅ 자동 생성 |
| ERD/DB 설계 | ❌ | ✅ 자동 생성 |
| AI 구현 인계 패키지 | ❌ | ✅ 자동 생성 |
| 설계 품질 자동 검증 | ❌ | ✅ 92/100 점수 |

# 딸깍(ddalggak) — 기능 완전 가이드

> **GSD가 할 수 있는 모든 것 + GSD가 못하는 것**  
> 프로젝트 시작부터 배포까지, 스크린샷으로 UI 생성부터 자동 버그수정까지 하나의 CLI로.

---

## GSD랑 뭐가 다른데?

| 기능 | GSD | 딸깍 |
|---|---|---|
| 프로젝트 생성 / 로드맵 | ✅ | ✅ |
| Phase 계획 / 실행 | ✅ | ✅ **+ 실패 시 자동 재시도** |
| 버그 디버깅 | ✅ | ✅ **+ 수정 이력 자동 저장** |
| 코드 리뷰 | ✅ | ✅ **+ 멀티 AI 리뷰** |
| UI Phase 계획 | ✅ (문서만) | ✅ **+ 실제 코드까지 생성** |
| 스크린샷 → 코드 생성 | ❌ | ✅ |
| 화면 비교 (visual regression) | ❌ | ✅ |
| 빌드/타입/lint 자동 검증 | ❌ | ✅ |
| 실패 시 자동 수정 루프 | ❌ | ✅ |
| 실행 전 되돌리기 (rollback) | ❌ | ✅ |
| 비용 추적 (token usage) | ❌ | ✅ |
| 왜 됐고 왜 실패했는지 증거 팩 | ❌ | ✅ |

---

## 기능 그룹 별 설명

---

### 🌟 0. 설계 문서 자동 생성 (딸깍 독보적 기능)

**아이디어 → 세계표준 설계 문서 패키지**

```
/ddk:design  (딸깍:설계)  "배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"
```

5~10분 인터뷰 후 **10개 설계 문서**가 자동으로 생성된다:

```
design-package/
├── 01-srs.md           ← 소프트웨어 요구사항 명세 (IEEE 830 / TTA 표준)
├── 02-prd.md           ← 제품 요구사항 (Amazon PR-FAQ 스타일)
├── 03-architecture.md  ← 시스템 아키텍처 (C4 Model / ISO 42010)
├── 04-api-spec.yaml    ← API 명세 (OpenAPI 3.0)
├── 05-database-schema.md ← ERD + 스키마 설계
├── 06-security-design.md ← 보안 설계 (ISMS-P / OWASP Top 10)
├── 07-adr-set.md       ← 아키텍처 결정 기록 (ADR)
├── 08-test-strategy.md ← 테스트 전략 (TDD 포함)
├── 09-implementation-plan.md ← Phase별 구현 계획 (DORA 기준)
└── 10-ai-handoff.md    ← AI가 읽고 바로 구현 시작하는 인계 패키지
```

**GSD에는 이 기능이 없다.** GSD는 설계 문서를 사람이 직접 만들어야 한다.

```
# 기존 repo에 새 기능 설계 추가
/ddk:design  (딸깍:설계)  "결제 모듈 추가" --repo ./my-app

# 전자정부 표준 적용
/ddk:design  (딸깍:설계)  "민원 처리 시스템" --standard egov

# 금융 보안 기준 적용
/ddk:design  (딸깍:설계)  "핀테크 송금 서비스" --standard pci-dss

# 생성된 설계 품질 검증
/ddk:design-review  (딸깍:설계검증)  ./design-package/
# → 품질 점수: 92/100, 보완 권고 항목 표시
```

> 📖 상세 설명: [DESIGN-STUDIO.md](./DESIGN-STUDIO.md)

---

### 1. 새 프로젝트 시작

아이디어 → PROJECT.md → 요구사항 → 로드맵까지 한 번에.

```
/ddk:new-project  (딸깍:새프로젝트)  "쇼핑몰 앱 만들고 싶어. 상품 목록, 장바구니, 결제"
```

**만들어주는 것:**
- `.planning/PROJECT.md` — 프로젝트 맥락
- `.planning/REQUIREMENTS.md` — 기능 요구사항
- `.planning/ROADMAP.md` — Phase별 구현 계획
- `.planning/STATE.md` — 현재 진행 상태

---

### 2. Phase 계획 세우기

로드맵의 특정 Phase를 구체적인 구현 계획으로 만든다.

```
/ddk:plan-phase  (딸깍:계획)  1               # Phase 1 계획
/ddk:plan-phase  (딸깍:계획)  2 --research    # 리서치 포함
/ddk:plan-phase  (딸깍:계획)  3 --prd spec.md # PRD 파일 기반
```

**하는 일:** 리서치 → 계획 작성 → 계획 검증 → PLAN.md 생성  
**GSD 대비 개선:** 계획 생성 시 LLM 호출 기록 저장, 컨텍스트 예산 자동 관리

---

### 3. Phase 실행하기

계획대로 실제 코드를 작성한다.

```
/ddk:execute-phase  (딸깍:실행)  1               # Phase 1 전체 실행
/ddk:execute-phase  (딸깍:실행)  1 --wave 1      # 1번 웨이브만
/ddk:execute-phase  (딸깍:실행)  1 --interactive # 단계별 확인하며 실행
/ddk:execute-phase  (딸깍:실행)  1 --gaps-only   # 검증 실패 항목만 재실행
```

**하는 일:** 의존성 분석 → 병렬 실행 → 각 태스크 완료 확인  
**GSD 대비 개선:** 각 태스크 실행 전 자동 checkpoint 생성 → 실패 시 rollback 가능

---

### 4. Phase 검증하기

실행 결과가 실제로 목표를 달성했는지 확인한다.

```
/ddk:verify-work  (딸깍:검증)  1             # Phase 1 검증
/ddk:verify-work  (딸깍:검증)  --certify     # 검증 + 릴리즈 판정
```

**확인하는 것:** 목표 달성 여부 / 코드 품질 / 테스트 통과 / 보안  
**결과:** `READY` / `BLOCKED` / `MANUAL-REVIEW` 판정 + 이유 목록

---

### 5. UI 화면 만들기 (딸깍 고유 기능)

디자인 시안 이미지를 실제 동작하는 코드로 변환한다.

```
# 방법 1: 전체 파이프라인 한 번에
/ddk:ui-gen  (딸깍:화면생성) \
  --image ./mockup.png \
  --prompt "로그인 폼. 이메일/비밀번호 + 로그인 버튼" \
  --repo .

# 방법 2: UI Phase 전체 워크플로우 (설계 → 생성 → 검증)
/ddk:ui-phase  (딸깍:UI계획)  3
```

**생성 후 자동으로 하는 것:**
1. 내 프로젝트 폴더 구조/네이밍 규칙에 맞게 코드 정규화
2. 빌드 + 타입체크 + lint 실행
3. 브라우저로 실제 화면 캡처 → 원본과 비교
4. 차이가 너무 크면 자동 수정 시도

---

### 6. 화면 비교 (Visual Regression)

원본 디자인과 실제 구현이 얼마나 일치하는지 숫자로 보여준다.

```
/ddk:visual-check  (딸깍:화면비교)  --reference ./design.png --url http://localhost:3000
```

```
결과 예시:
SSIM 유사도:     94.2%  ✅
픽셀 차이:       3.1%   ✅
핵심 구역 매칭:  97.0%  ✅
누락 구역:       없음   ✅

→ PASS
```

---

### 7. 버그 디버깅

버그를 과학적으로 조사하고 수정한다.

```
/ddk:debug  (딸깍:디버그)  "로그인 버튼 클릭 시 콘솔에 에러 발생"
```

**하는 일:**
1. 증상 수집 (예상 동작 / 실제 동작 / 에러 메시지)
2. 코드베이스 조사 + 가설 수립
3. 근본 원인 발견 → 수정
4. 수정 전 자동 checkpoint → 실패 시 rollback 가능

**GSD 대비 개선:** 수정 시도마다 이전 컨텍스트(무엇을 시도했고 왜 실패했는지) 자동 인계

---

### 8. 코드 리뷰

작성한 코드를 여러 AI 관점에서 검토한다.

```
/ddk:review  (딸깍:리뷰)  --phase 2              # Phase 2 코드 리뷰
/ddk:review  (딸깍:리뷰)  --all                  # 모든 AI (Gemini, Claude, Codex) 동시 리뷰
/ddk:review  (딸깍:리뷰)  --phase 2 --gemini     # Gemini만 리뷰
/ddk:ui-review  (딸깍:화면감사)  --phase 3        # UI 품질 전용 감사
```

---

### 9. 테스트 추가 & 감사

테스트가 없는 곳에 테스트를 자동 생성하거나, 커버리지를 감사한다.

```
/ddk:add-tests  (딸깍:테스트추가)  --phase 2     # Phase 2 기능에 테스트 추가
/ddk:audit  (딸깍:테스트감사)                    # 전체 커버리지 감사 (빠진 테스트 찾기)
/ddk:uat-audit  (딸깍:UAT감사)                   # 사용자 검수 기준으로 감사
```

---

### 10. 배포 (Ship)

검증 완료 후 PR을 만들고 머지한다.

```
/ddk:ship  (딸깍:배포)  2                        # Phase 2 완료 → PR 생성 + 리뷰
/ddk:ship  (딸깍:배포)  v1.0                     # v1.0 마일스톤 배포
```

**하는 일:** branch push → PR body 자동 작성 → 리뷰 요청 → 머지 추적

---

### 11. 잘못됐으면 되돌리기

```
/ddk:rollback  (딸깍:롤백)  --phase 2            # Phase 2 실행 전 상태로 복원
/ddk:rollback  (딸깍:롤백)  --case C-001 --to 0  # UI 생성 전 상태로 복원
/ddk:rollback  (딸깍:롤백)  --list               # 복원 가능한 checkpoint 목록
```

딸깍은 **모든 중요한 작업 전에 자동으로 checkpoint를 만든다.** 뭔가 잘못되면 언제든지 되돌릴 수 있다.

---

### 12. 현재 상태 확인

```
/ddk:status  (딸깍:상태)                         # 지금 어디까지 왔는지
/ddk:stats  (딸깍:통계)                          # 전체 통계 (phase 완료율, 테스트 수 등)
/ddk:health  (딸깍:건강)                         # 프로젝트 건강 상태
/ddk:progress  (딸깍:진행률)                     # 마일스톤 진행률
```

---

### 13. 환경 점검 (Preflight)

뭔가 안 되기 전에 미리 환경 확인.

```
/ddk:preflight  (딸깍:환경점검)

# Python 3.12+ 있어? ✅
# LLM API 키 설정했어? ❌  → export DDK_LLM_API_KEY=...
# Playwright 설치했어? ❌  → playwright install chromium
# Node.js 있어? ✅
# Git 있어? ✅
# 쓰기 권한 있어? ✅
```

---

### 14. 코드베이스 분석

기존 프로젝트를 빠르게 이해한다.

```
/ddk:map  (딸깍:코드맵)                          # 전체 구조 파악
/ddk:map  (딸깍:코드맵)  --focus auth             # 인증 관련 코드만
/ddk:research  (딸깍:리서치)  "JWT 인증 구현 방법" # 도메인 리서치
```

---

### 15. 기타 유틸리티

```
/ddk:todo  (딸깍:할일)  add "결제 모듈 구현"      # 할 일 추가
/ddk:todo  (딸깍:할일)  check                    # 할 일 현황
/ddk:backlog  (딸깍:백로그)  add "다크모드 지원"   # 백로그 추가
/ddk:note  (딸깍:메모)  "API 키는 env에 넣어야 함" # 메모
/ddk:report  (딸깍:리포트)  --phase 2            # Phase 2 상세 리포트
/ddk:benchmark  (딸깍:벤치마크)                  # GSD 대비 성능 측정
```

---

## 전체 명령 목록

| 명령 (슬래시커맨드) | 한국어 표시 | 하는 일 | GSD 대응 |
|---|---|---|---|
| `/ddk:design` | 딸깍:설계 | **아이디어 → 10개 설계 문서 자동 생성** | **GSD에 없음** |
| `/ddk:design-review` | 딸깍:설계검증 | 설계 품질 자동 검증 | **GSD에 없음** |
| `/ddk:design-update` | 딸깍:설계수정 | 설계에 요구사항 추가 | **GSD에 없음** |
| `/ddk:design-export` | 딸깍:설계내보내기 | PDF/Notion/Confluence 내보내기 | **GSD에 없음** |
| `/ddk:new-project` | 딸깍:새프로젝트 | 새 프로젝트 초기화 | `gsd:new-project` |
| `/ddk:new-milestone` | 딸깍:새마일스톤 | 새 마일스톤 | `gsd:new-milestone` |
| `/ddk:complete-milestone` | 딸깍:마일스톤완료 | 마일스톤 완료 | `gsd:complete-milestone` |
| `/ddk:audit-milestone` | 딸깍:마일스톤감사 | 마일스톤 감사 | `gsd:audit-milestone` |
| `/ddk:plan-phase` | 딸깍:계획 | Phase 계획 생성 | `gsd:plan-phase` |
| `/ddk:execute-phase` | 딸깍:실행 | Phase 실행 | `gsd:execute-phase` |
| `/ddk:verify-work` | 딸깍:검증 | Phase 검증 | `gsd:verify-work` |
| `/ddk:research-phase` | 딸깍:리서치 | Phase 리서치 | `gsd:research-phase` |
| `/ddk:discuss-phase` | 딸깍:토론 | Phase 토론/가정 분석 | `gsd:discuss-phase` |
| `/ddk:add-phase` | 딸깍:계획추가 | Phase 추가 | `gsd:add-phase` |
| `/ddk:remove-phase` | 딸깍:계획제거 | Phase 제거 | `gsd:remove-phase` |
| `/ddk:plan-gaps` | 딸깍:갭계획 | 갭 계획 | `gsd:plan-milestone-gaps` |
| `/ddk:validate-phase` | 딸깍:계획검증 | Phase 검증 | `gsd:validate-phase` |
| `/ddk:debug` | 딸깍:디버그 | 버그 디버깅 | `gsd:debug` |
| `/ddk:forensics` | 딸깍:포렌식 | 코드 포렌식 | `gsd:forensics` |
| `/ddk:review` | 딸깍:리뷰 | 코드 리뷰 (멀티 AI) | `gsd:review` |
| `/ddk:ui-phase` | 딸깍:UI계획 | UI Phase 계획 | `gsd:ui-phase` |
| `/ddk:ui-gen` | 딸깍:화면생성 | 스크린샷 → 코드 생성 | **GSD에 없음** |
| `/ddk:visual-check` | 딸깍:화면비교 | 화면 비교 (visual regression) | **GSD에 없음** |
| `/ddk:ui-review` | 딸깍:화면감사 | UI 품질 감사 | `gsd:ui-review` |
| `/ddk:run` | 딸깍:전체실행 | UI 전체 파이프라인 | **GSD에 없음** |
| `/ddk:validate` | 딸깍:검사 | 빌드/타입/lint/런타임 검증 | **GSD에 없음** |
| `/ddk:normalize` | 딸깍:정규화 | 코드 정규화 | **GSD에 없음** |
| `/ddk:auto-fix` | 딸깍:자동수정 | 자동 수정 루프 | **GSD에 없음** |
| `/ddk:certify` | 딸깍:인증 | 릴리즈 인증 (evidence 기반) | **GSD에 없음** |
| `/ddk:ship` | 딸깍:배포 | PR 생성 + 배포 | `gsd:ship` |
| `/ddk:rollback` | 딸깍:롤백 | 되돌리기 | **GSD에 없음** |
| `/ddk:map` | 딸깍:코드맵 | 코드베이스 분석 | `gsd:map-codebase` |
| `/ddk:research` | 딸깍:리서치 | 도메인 리서치 | `gsd:research-phase` |
| `/ddk:add-tests` | 딸깍:테스트추가 | 테스트 자동 생성 | `gsd:add-tests` |
| `/ddk:audit` | 딸깍:테스트감사 | 테스트 커버리지 감사 | `gsd:audit` |
| `/ddk:uat-audit` | 딸깍:UAT감사 | UAT 감사 | `gsd:audit-uat` |
| `/ddk:status` | 딸깍:상태 | 현재 상태 | `gsd:next` + `gsd:progress` |
| `/ddk:stats` | 딸깍:통계 | 통계 | `gsd:stats` |
| `/ddk:health` | 딸깍:건강 | 프로젝트 건강 상태 | `gsd:health` |
| `/ddk:report` | 딸깍:리포트 | 상세 리포트 | `gsd:session-report` |
| `/ddk:benchmark` | 딸깍:벤치마크 | GSD 대비 성능 측정 | **GSD에 없음** |
| `/ddk:preflight` | 딸깍:환경점검 | 환경 점검 | **GSD에 없음** |
| `/ddk:init` | 딸깍:초기화 | 환경 초기화 | (gsd 설정의 일부) |
| `/ddk:workspace` | 딸깍:워크스페이스 | 워크스페이스 관리 | `gsd:new/list/remove-workspace` |
| `/ddk:todo` | 딸깍:할일 | 할 일 관리 | `gsd:add-todo`, `gsd:check-todos` |
| `/ddk:backlog` | 딸깍:백로그 | 백로그 관리 | `gsd:add/review-backlog` |
| `/ddk:note` | 딸깍:메모 | 메모 | `gsd:note` |
| `/ddk:auto` | 딸깍:자동 | 자율 실행 모드 | `gsd:autonomous`, `gsd:fast` |
| `/ddk:profile` | 딸깍:프로파일 | 사용자 프로파일 | `gsd:profile-user` |
| `/ddk:workstreams` | 딸깍:워크스트림 | 워크스트림 관리 | `gsd:workstreams` |

---

## 딸깍이 GSD보다 나은 핵심 이유

### ① 모든 작업에 자동 checkpoint

GSD는 뭔가 잘못되면 수동으로 git revert해야 한다.  
딸깍은 **모든 중요한 작업 전에 자동으로 저장점을 만들어서 언제든 되돌릴 수 있다.**

### ② 왜 됐고 왜 실패했는지 증거를 남긴다

GSD는 "됐다/안 됐다"만 알 수 있다.  
딸깍은 **어떤 LLM을 어떤 컨텍스트로 호출했는지, 무엇을 시도했는지, 어디서 막혔는지** 전부 기록한다.

### ③ 실패하면 스스로 고친다

GSD는 실패하면 사람이 다시 실행해야 한다.  
딸깍은 **실패 원인을 분류해서 자동으로 3번까지 다른 방법으로 수정 시도한다.**

### ④ 화면이 맞는지 숫자로 확인한다

GSD는 UI 코드를 생성해도 화면이 맞는지 확인하지 않는다.  
딸깍은 **실제 브라우저에서 화면을 캡처해서 원본과 SSIM으로 비교한다.**

### ⑤ 비용 추적

GSD는 LLM 호출 비용을 추적하지 않는다.  
딸깍은 **모든 LLM 호출의 토큰 수와 비용을 기록한다.**

---

## 가장 자주 쓰는 시나리오

### 시나리오 A: 아이디어 → 설계 → 구현 (딸깍 핵심 플로우)
```
/ddk:design  (딸깍:설계)  "배달 앱. 식당 목록, 주문, 실시간 추적"
/ddk:new-project  (딸깍:새프로젝트)  --from-design ./design-package
/ddk:plan-phase  (딸깍:계획)  1
/ddk:execute-phase  (딸깍:실행)  1
```

### 시나리오 B: 새 기능 추가 (GSD 스타일 호환)
```
/ddk:plan-phase  (딸깍:계획)  3               # Phase 3 계획
/ddk:execute-phase  (딸깍:실행)  3             # 실행
/ddk:verify-work  (딸깍:검증)  3               # 검증
/ddk:ship  (딸깍:배포)  3                      # PR
```

### 시나리오 C: 디자인 시안으로 UI 만들기 (딸깍 고유)
```
/ddk:ui-gen  (딸깍:화면생성)  --image mockup.png --prompt "대시보드 화면" --repo .
# → 코드 생성 + 검증 + 화면 비교 + 자동 수정 자동 실행
```

### 시나리오 D: 버그 수정
```
/ddk:debug  (딸깍:디버그)  "결제 완료 후 장바구니가 비워지지 않음"
# → 조사 → 원인 발견 → 수정 → 검증 → 완료
```

### 시나리오 E: 기존 코드 리뷰
```
/ddk:review  (딸깍:리뷰)  --phase 2 --all     # 모든 AI로 동시에 리뷰
```

---

## 지원 AI 도구 & 설치 방법

딸깍은 **Claude Code, GitHub Copilot, Gemini CLI, OpenCode, Codex** 모두에서 동작한다.  
핵심 엔진(`ddk` CLI)은 동일하고, 각 도구에 맞는 어댑터만 설치하면 된다.

### 1단계: ddk CLI 설치 (공통)

```bash
# uv 사용 (권장)
uv tool install ddalggak

# 또는 pip
pip install ddalggak

# 확인
ddk --version
ddk preflight
```

### 2단계: AI 도구별 어댑터 설치

```bash
# Claude Code
ddk install --adapter claude
# → .claude/commands/ddk/ 폴더 생성
# → .mcp.json에 MCP 서버 등록
# → 이후: /project:ddk/design "아이디어" 로 사용

# GitHub Copilot
ddk install --adapter copilot
# → .github/skills/ddalggak-*/ 폴더 생성
# → .github/agents/ddalggak-*.md 생성
# → 이후: /ddk:design (딸깍:설계) "아이디어" 로 사용

# Gemini CLI
ddk install --adapter gemini
# → .gemini/extensions/ddalggak/extension.json 생성
# → 이후: @ddalggak ddk_design idea="아이디어" 로 사용

# OpenCode
ddk install --adapter opencode
# → opencode.json MCP 서버 등록
# → 이후: MCP tool로 사용

# Codex (OpenAI)
ddk install --adapter codex
# → .codex/instructions.md 생성
# → 이후: ddk 직접 실행

# 전체 한 번에
ddk install --adapter all
```

### 도구별 같은 명령 비교

| 작업 | Claude Code | Copilot | Gemini CLI |
|------|-------------|---------|------------|
| 설계 문서 생성 | `/project:ddk/design "아이디어"` | `/ddk:design "아이디어"` | `@ddalggak ddk_design idea="아이디어"` |
| Phase 실행 | `/project:ddk/execute-phase 2` | `/ddk:execute-phase 2` | `@ddalggak ddk_execute_phase phase=2` |
| 버그 수정 | `/project:ddk/debug "버그"` | `/ddk:debug "버그"` | `@ddalggak ddk_debug description="버그"` |
| 롤백 | `/project:ddk/rollback --phase 2` | `/ddk:rollback --phase 2` | `@ddalggak ddk_rollback target="phase-2"` |

> 상세 설치 가이드: [docs/design/10-multi-tool-adapter.md](./design/10-multi-tool-adapter.md)

# 딸깍(ddalggak) 사용자 가이드

> **설계 기반 명세서** — 이 문서는 현재 설계(`docs/design/`)를 그대로 구현했을 때 개발자가 사용할 수 있는 기능과 인터페이스를 기술합니다.

---

## 목차

1. [딸깍이란](#1-딸깍이란)
2. [전제 조건 및 환경](#2-전제-조건-및-환경)
3. [설치](#3-설치)
4. [설정(Configuration)](#4-설정configuration)
5. [첫 실행 — Preflight Check](#5-첫-실행--preflight-check)
6. [핵심 워크플로우](#6-핵심-워크플로우)
7. [CLI 명령 레퍼런스](#7-cli-명령-레퍼런스)
8. [전체 파이프라인 예제](#8-전체-파이프라인-예제)
9. [출력 아티팩트 가이드](#9-출력-아티팩트-가이드)
10. [설정 파일 상세](#10-설정-파일-상세)
11. [롤백 및 복구](#11-롤백-및-복구)
12. [벤치마크 및 스코어카드](#12-벤치마크-및-스코어카드)
13. [고급 사용법](#13-고급-사용법)
14. [트러블슈팅](#14-트러블슈팅)
15. [용어 사전](#15-용어-사전)

---

## 1. 딸깍이란

`딸깍`은 **스크린샷 + 프롬프트 → repo-aligned 코드 생성 → sandboxed 검증 → 자동 수정 → 인증** 루프를 하나의 CLI로 실행하는 self-correcting code generation tool이다.

```
[스크린샷 / 레퍼런스 이미지]
          +
[자연어 프롬프트]                ──▶  ddk run  ──▶  [검증된 코드]
          +                                          [evidence pack]
[대상 repo 경로]                                     [release decision]
```

### 딸깍이 하는 것

| 단계 | 하는 일 |
|---|---|
| ingest | 이미지, 프롬프트, repo 경로를 구조화된 artifact로 저장 |
| analyze | repo의 framework/naming/design-token 관례를 스캔하고, 이미지에서 semantic intent를 추출 |
| generate | repo 관례에 맞는 컴포넌트/페이지 코드를 생성 |
| normalize | 생성된 코드의 naming/import/token drift를 repo 표준에 맞게 정규화 |
| validate | sandbox에서 build, typecheck, lint, runtime smoke, console error를 검증 |
| visual-check | reference 스크린샷과 생성된 화면을 비교하여 시각적 일치를 확인 |
| auto-fix | 실패를 분류하고 bounded retry 안에서 자동 수정 |
| certify | 모든 결과를 종합해 `ready / blocked / manual-review` 판정 |

### 딸깍이 하지 않는 것 (v1 범위 외)

- 범용 AI 코딩 워크플로우 전체를 대체하지 않는다.
- API binding, domain state, async flow 복잡한 생성은 v1 외다.
- zero-friction one-click consumer 경험은 v1 목표가 아니다.
- GSD와의 총체적 우월성을 주장하지 않는다.

---

## 2. 전제 조건 및 환경

### 필수

| 항목 | 최소 버전 | 확인 명령 |
|---|---|---|
| Python | 3.12+ | `python --version` |
| uv | 최신 | `uv --version` |
| Node.js | 20+ | `node --version` |
| Git | 2.30+ | `git --version` |
| Playwright (Chromium) | 최신 | `playwright --version` |
| LLM API Key | — | 환경 변수 `DDK_LLM_API_KEY` |

### 선택

| 항목 | 용도 |
|---|---|
| Docker | sandbox isolation 강화 (기본은 ephemeral git worktree) |
| pnpm / yarn | npm 외 package manager 사용 시 |

### 지원 대상 Repo (v1 / P0)

| 대상 | 지원 여부 |
|---|---|
| React + Vite + TypeScript | ✅ P0 핵심 |
| React + Next.js + TypeScript | ✅ v1 |
| Vue + TypeScript | 🔜 vNext |
| plain Node.js / Python | ❌ v1 외 |

---

## 3. 설치

```bash
# uv를 사용한 설치
git clone https://github.com/your-org/ddalggak.git
cd ddalggak
uv sync

# CLI entrypoint 확인
uv run ddk --help
```

또는 PyPI에서 설치:

```bash
pip install ddalggak
ddk --help
```

### Playwright Chromium 설치

```bash
uv run playwright install chromium
```

---

## 4. 설정(Configuration)

### 4.1 API Key 설정

```bash
export DDK_LLM_API_KEY=sk-...           # OpenAI / Anthropic 등
export DDK_LLM_PROVIDER=anthropic       # anthropic | openai | azure
export DDK_LLM_MODEL=claude-3-5-sonnet  # 기본 모델
```

또는 `.env` 파일:

```env
DDK_LLM_API_KEY=sk-...
DDK_LLM_PROVIDER=anthropic
DDK_LLM_MODEL=claude-3-5-sonnet
```

### 4.2 프로젝트 설정 초기화

```bash
# 대상 repo에서 딸깍 workspace 초기화
cd /path/to/my-react-app
ddk init
```

`ddk init` 실행 후 생성되는 파일:

```
my-react-app/
└── .ddk/
    ├── config.json          # 프로젝트별 설정
    ├── schema-version.json  # artifact schema 버전
    └── cases/               # case 결과물 저장소 (auto-generated)
```

### 4.3 `.ddk/config.json` 예시

```json
{
  "project": {
    "name": "my-react-app",
    "repo_path": ".",
    "framework": "react-vite-typescript"
  },
  "llm": {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet",
    "fast_model": "claude-haiku",
    "temperature": 0.2
  },
  "sandbox": {
    "mode": "git-worktree",
    "network": "deny",
    "allowed_commands": ["npm run build", "npm run typecheck", "npm run lint"]
  },
  "visual": {
    "viewport": { "width": 1440, "height": 900 },
    "thresholds": {
      "ssim": 0.92,
      "changed_pixel_ratio": 0.05,
      "critical_region_overlap": 0.90,
      "missing_critical_regions": 0
    }
  },
  "auto_fix": {
    "max_retries": 3
  }
}
```

---

## 5. 첫 실행 — Preflight Check

딸깍의 모든 명령은 **preflight green** 없이는 실행되지 않는다.

```bash
ddk preflight
```

**성공 시 출력:**

```
딸깍 Preflight Check
────────────────────────────────────────
✓  Python 3.12.3
✓  uv 0.4.1
✓  LLM API key (DDK_LLM_API_KEY, anthropic)
✓  Playwright Chromium 1.44
✓  Node.js 20.11.0
✓  Git 2.44.0
✓  Repo path: /Users/me/my-react-app (git repo ✓)
✓  Write permission: .ddk/
✓  Sandbox mode: git-worktree
────────────────────────────────────────
All 9 checks passed. Ready to run.
```

**실패 시 출력:**

```
딸깍 Preflight Check
────────────────────────────────────────
✓  Python 3.12.3
✓  uv 0.4.1
✗  LLM API key not found (DDK_LLM_API_KEY)
   → Fix: export DDK_LLM_API_KEY=<your-api-key>
✗  Playwright Chromium not installed
   → Fix: uv run playwright install chromium
✓  Node.js 20.11.0
────────────────────────────────────────
2 checks failed. Fix above issues and re-run 'ddk preflight'.
```

### Preflight 옵션

```bash
ddk preflight --json          # JSON 형식 출력
ddk preflight --fix           # 가능한 항목 자동 수정 시도
```

---

## 6. 핵심 워크플로우

### 6.1 기본 워크플로우 (one-command)

```bash
ddk run \
  --image ./designs/dashboard.png \
  --prompt "사용자 대시보드 페이지. 왼쪽에 사이드바, 상단 헤더, 중앙에 카드 그리드." \
  --repo .
```

`ddk run`은 아래 8단계를 순서대로 실행한다:

```
ingest → analyze → generate → normalize → validate → visual-check → auto-fix → certify
```

### 6.2 단계별 실행 (개별 명령)

단계를 직접 제어하고 싶을 때:

```bash
ddk ingest --image ./designs/dashboard.png --prompt "..." --repo .
# → case ID 출력: C-20240326-001

ddk analyze --case C-20240326-001
ddk generate --case C-20240326-001
ddk normalize --case C-20240326-001
ddk validate --case C-20240326-001
ddk visual-check --case C-20240326-001
ddk auto-fix --case C-20240326-001
ddk certify --case C-20240326-001
```

### 6.3 인터랙티브 모드

```bash
ddk run --interactive
# 각 단계 결과를 보고 계속할지 중단할지 결정 가능
```

---

## 7. CLI 명령 레퍼런스

### `ddk init`

대상 repo에 딸깍 workspace를 초기화한다.

```
ddk init [OPTIONS]

Options:
  --repo PATH           초기화할 repo 경로 (기본: 현재 디렉토리)
  --force               기존 설정 덮어쓰기
  --json                JSON 형식 출력
```

**예:**
```bash
cd /path/to/my-app
ddk init
ddk init --repo /path/to/my-app
```

---

### `ddk preflight`

환경 전제 조건을 검사하고 remediation hint를 출력한다.

```
ddk preflight [OPTIONS]

Options:
  --repo PATH           검사할 repo 경로 (기본: 현재 디렉토리)
  --fix                 가능한 항목 자동 수정 시도
  --json                JSON 형식 출력
  --skip-preflight      ⚠️  CI 환경에서만 허용. 모든 검사를 건너뜀
```

---

### `ddk ingest`

이미지, 프롬프트, repo 경로를 받아 케이스 artifact를 생성한다.

```
ddk ingest [OPTIONS]

Options:
  --image PATH          [필수] 레퍼런스 스크린샷 경로 (PNG/JPG/WEBP)
  --prompt TEXT         [필수] 생성 의도 설명
  --repo PATH           [필수] 대상 repo 경로
  --reference TEXT      추가 참고 메모 (선택)
  --case-id TEXT        케이스 ID 직접 지정 (기본: 자동 생성)
  --json                JSON 형식 출력
```

**예:**
```bash
ddk ingest \
  --image ./mockups/login-v3.png \
  --prompt "소셜 로그인 버튼 포함 로그인 페이지. 이메일/비밀번호 폼과 구글/깃허브 버튼." \
  --repo /path/to/my-app

# 출력:
# Case created: C-20240326-001
# Artifact: .ddk/cases/C-20240326-001/input.json
```

**생성 artifact:**
```
.ddk/cases/C-20240326-001/
└── input.json        # CaseInput Pydantic model
```

---

### `ddk analyze`

Repo convention을 스캔하고 이미지에서 semantic intent를 추출한다.

```
ddk analyze [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --skip-repo-scan      repo 스캔 건너뜀 (기존 profile 재사용)
  --skip-intent         intent 추출 건너뜀
  --json                JSON 형식 출력
```

**예:**
```bash
ddk analyze --case C-20240326-001

# 출력:
# [repo_scan] Framework: react-vite-typescript
# [repo_scan] Design tokens: 47 tokens found (Tailwind)
# [repo_scan] Components: 23 existing primitives
# [intent_extract] Layout regions: header, sidebar, main-grid (3 cards)
# [intent_extract] Confidence: 0.84
# [intent_extract] Unresolved: card-click-behavior (2 items)
#
# Artifacts:
#   .ddk/cases/C-20240326-001/repo-profile.json
#   .ddk/cases/C-20240326-001/intent-graph.json
```

**생성 artifact:**
```
.ddk/cases/C-20240326-001/
├── repo-profile.json    # RepoProfile: framework, naming, tokens, layout
└── intent-graph.json    # IntentGraph: regions, components, confidence, unresolved
```

---

### `ddk generate`

intent graph와 repo profile 기반으로 코드를 생성한다.

```
ddk generate [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --target PATH         생성 파일 경로 (기본: analyze 결과 기반 자동 결정)
  --dry-run             실제 파일 변경 없이 생성 계획만 출력
  --json                JSON 형식 출력
```

**예:**
```bash
ddk generate --case C-20240326-001

# 출력:
# [plan] 3 files to generate
#   src/pages/Login.tsx       (new)
#   src/components/SocialLoginButton.tsx  (new)
#   src/pages/Login.test.tsx  (new)
# [generate] src/pages/Login.tsx ✓
# [generate] src/components/SocialLoginButton.tsx ✓
# [generate] src/pages/Login.test.tsx ✓
#
# Artifact: .ddk/cases/C-20240326-001/generated-artifact.json
```

**dry-run 예:**
```bash
ddk generate --case C-20240326-001 --dry-run
# 파일을 생성하지 않고 계획만 표시
```

---

### `ddk normalize`

생성된 코드의 naming/import/token/file placement를 repo 표준에 맞게 정규화한다.

```
ddk normalize [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --strict              모든 convention drift를 오류로 처리
  --json                JSON 형식 출력
```

**예:**
```bash
ddk normalize --case C-20240326-001

# 출력:
# [normalize] Checking 3 files against repo conventions...
# [normalize] Fixed: import ordering in Login.tsx (3 fixes)
# [normalize] Fixed: color token `blue-600` → `primary-600` (2 fixes)
# [normalize] Fixed: component name `loginBtn` → `LoginButton`
# [normalize] Convention drift: 6 fixes applied
#
# Artifact: .ddk/cases/C-20240326-001/normalization-report.json
```

---

### `ddk validate`

sandbox 환경에서 build, typecheck, lint, runtime smoke, console error를 검증한다.

```
ddk validate [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --checks TEXT         실행할 검사 목록 (기본: build,typecheck,lint,runtime,console)
                        예: --checks build,typecheck
  --timeout INT         sandbox 실행 timeout 초 (기본: 120)
  --json                JSON 형식 출력
```

**예:**
```bash
ddk validate --case C-20240326-001

# 출력:
# [sandbox] Creating ephemeral worktree...
# [validate] build         ✓  (12.3s)
# [validate] typecheck     ✓  (4.1s)
# [validate] lint          ✓  (2.8s)
# [validate] runtime-smoke ✓  App started on :5173 (3.2s)
# [validate] console-errors 0 errors, 1 warning
#   ⚠ Warning: [React] useEffect dependency array missing (Login.tsx:34)
# [sandbox] Worktree cleaned up.
#
# Validation: PASS
# Artifact: .ddk/cases/C-20240326-001/runtime-validation-report.json
```

**실패 예:**
```bash
# [validate] typecheck     ✗
#   Error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'
#   Location: src/pages/Login.tsx:28:18
#
# Validation: FAIL (taxonomy: TYPE_ERROR)
# → Run 'ddk auto-fix --case C-20240326-001' to attempt auto-fix
```

---

### `ddk visual-check`

reference 이미지와 생성된 화면 스크린샷을 비교한다.

```
ddk visual-check [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --reference PATH      레퍼런스 이미지 경로 (기본: ingest 시 입력한 이미지)
  --viewport WxH        viewport 크기 (기본: 1440x900)
  --threshold PROFILE   임계치 프로파일 (기본: config.json의 visual.thresholds)
  --json                JSON 형식 출력
```

**예:**
```bash
ddk visual-check --case C-20240326-001

# 출력:
# [visual] Launching Chromium...
# [visual] Capturing screenshot at 1440x900...
# [visual] Computing diff...
#
# SSIM:                  0.94  ✓  (threshold: 0.92)
# Changed pixel ratio:   3.2%  ✓  (threshold: 5%)
# Critical region overlap: 0.96  ✓  (threshold: 0.90)
# Missing critical regions: 0   ✓
#
# Visual check: PASS
#
# Artifacts:
#   .ddk/cases/C-20240326-001/screenshots/reference.png
#   .ddk/cases/C-20240326-001/screenshots/current.png
#   .ddk/cases/C-20240326-001/screenshots/diff.png
#   .ddk/cases/C-20240326-001/visual-regression-report.json
```

**실패 예:**
```bash
# SSIM:                  0.78  ✗  (threshold: 0.92)
# Changed pixel ratio:  18.4%  ✗  (threshold: 5%)
# Critical region overlap: 0.72  ✗  (threshold: 0.90)
#   Missing: primary-cta-button
#
# Visual check: FAIL
# → Open .ddk/cases/C-20240326-001/screenshots/diff.png to inspect
# → Run 'ddk auto-fix --case C-20240326-001' to attempt auto-fix
```

---

### `ddk auto-fix`

실패를 분류하고 bounded retry 안에서 자동으로 수정한다.

```
ddk auto-fix [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --max-retries INT     최대 재시도 횟수 (기본: config.json의 auto_fix.max_retries)
  --fix-type TEXT       특정 failure class만 수정
                        (build | type | lint | runtime | visual | all)
  --json                JSON 형식 출력
```

**예:**
```bash
ddk auto-fix --case C-20240326-001

# 출력:
# [auto-fix] Failures to fix: TYPE_ERROR (1), VISUAL_MISMATCH (1)
#
# Attempt 1/3
# [checkpoint] ddk/fix/C-20240326-001/attempt-1 created
# [fix] TYPE_ERROR → patch: src/pages/Login.tsx:28 (type cast)
# [validate] typecheck ✓
# [visual-check] SSIM 0.91 ✗ (threshold: 0.92)
#
# Attempt 2/3
# [checkpoint] ddk/fix/C-20240326-001/attempt-2 created
# [fix] VISUAL_MISMATCH → layout adjustment: flex-direction, gap
# [validate] build ✓, typecheck ✓, lint ✓
# [visual-check] SSIM 0.95 ✓
#
# Auto-fix: SUCCESS (2 attempts)
# Artifact: .ddk/cases/C-20240326-001/fix-attempts.json
```

**Budget exhausted 예:**
```bash
# Attempt 3/3
# [fix] VISUAL_MISMATCH → ... (same class, non-improving)
# [visual-check] SSIM 0.80 ✗
#
# Auto-fix: EXHAUSTED
# Status: manual-review-required
# Checkpoint to restore: ddk/fix/C-20240326-001/attempt-0 (pre-fix state)
# → Run 'ddk rollback --case C-20240326-001' to restore to pre-fix state
# → Review .ddk/cases/C-20240326-001/fix-attempts.json for details
```

---

### `ddk certify`

모든 validation 결과를 종합해 release decision을 발급한다.

```
ddk certify [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --json                JSON 형식 출력
```

**예:**
```bash
ddk certify --case C-20240326-001

# 출력:
# ────────────────────────────────────────
# 딸깍 Release Decision
# Case: C-20240326-001
# ────────────────────────────────────────
# Runtime validation:   PASS ✓
# Visual regression:    PASS ✓
# Auto-fix:             SUCCESS (2 attempts) ✓
# Known Sev0/Sev1:      0 ✓
# Release-gating flaky: 0 ✓
# ────────────────────────────────────────
# Decision: READY ✅
#
# Evidence pack: .ddk/cases/C-20240326-001/evidence-pack/
# Artifact: .ddk/cases/C-20240326-001/release-decision.json
```

**Blocked 예:**
```bash
# Decision: BLOCKED 🚫
# Blockers:
#   [SEV1] Visual regression FAIL: SSIM 0.78 (threshold: 0.92)
#   [SEV1] Missing critical region: primary-cta-button
#
# Action required:
#   1. Review diff: .ddk/cases/C-20240326-001/screenshots/diff.png
#   2. Fix manually or adjust reference image
#   3. Re-run: ddk validate && ddk visual-check && ddk certify --case C-20240326-001
```

---

### `ddk run`

전체 파이프라인(ingest → certify)을 한 번에 실행한다.

```
ddk run [OPTIONS]

Options:
  --image PATH          [필수] 레퍼런스 스크린샷 경로
  --prompt TEXT         [필수] 생성 의도 설명
  --repo PATH           [필수] 대상 repo 경로
  --reference TEXT      추가 참고 메모 (선택)
  --max-retries INT     auto-fix 최대 재시도 (기본: 3)
  --interactive         각 단계 후 확인 prompt
  --skip-visual         visual-check 건너뜀
  --skip-preflight      ⚠️  CI에서만. preflight 건너뜀
  --json                JSON 형식 출력
  --output-dir PATH     evidence pack 저장 경로 (기본: .ddk/cases/)
```

**예:**
```bash
ddk run \
  --image ./designs/dashboard.png \
  --prompt "사이드바 + 헤더 + 카드 그리드 구성의 대시보드 페이지" \
  --repo .

# 출력:
# Case: C-20240326-001
# ──────────────────────────────────────
# [1/8] ingest        ✓
# [2/8] analyze       ✓  (repo: react-vite-ts, tokens: 47, intent: 0.84)
# [3/8] generate      ✓  (3 files)
# [4/8] normalize     ✓  (6 fixes)
# [5/8] validate      ✓  (build/type/lint/runtime pass)
# [6/8] visual-check  ✓  (SSIM 0.94)
# [7/8] auto-fix      -  (not needed)
# [8/8] certify       ✓  READY
# ──────────────────────────────────────
# Decision: READY ✅
# Evidence pack: .ddk/cases/C-20240326-001/
```

---

### `ddk rollback`

auto-fix 전 상태로 파일을 복원한다.

```
ddk rollback [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --to INT              복원할 attempt 번호 (기본: 0 = pre-fix state)
  --list                사용 가능한 checkpoint 목록 표시
  --dry-run             실제 변경 없이 어떤 파일이 복원되는지 표시
```

**예:**
```bash
# 사용 가능한 체크포인트 목록 확인
ddk rollback --case C-20240326-001 --list
# Checkpoints:
#   0  (pre-fix)   ddk/fix/C-20240326-001/attempt-0  2024-03-26 12:10:05
#   1  (attempt-1) ddk/fix/C-20240326-001/attempt-1  2024-03-26 12:10:45
#   2  (attempt-2) ddk/fix/C-20240326-001/attempt-2  2024-03-26 12:11:20

# pre-fix 상태로 완전 복원
ddk rollback --case C-20240326-001 --to 0

# 출력:
# [rollback] Restoring to attempt-0 (pre-fix state)...
# [rollback] Files restored:
#   src/pages/Login.tsx              (reverted)
#   src/components/SocialLoginButton.tsx  (removed)
# [rollback] Repo status: clean ✓
# Rollback complete.
```

---

### `ddk report`

케이스의 evidence pack과 결과를 터미널에 출력한다.

```
ddk report [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --section TEXT        특정 섹션만 출력
                        (summary | runtime | visual | fix-history | scorecard | all)
  --json                JSON 형식 출력
  --open                브라우저에서 HTML 리포트 열기 (지원 시)
```

**예:**
```bash
ddk report --case C-20240326-001 --section summary

ddk report --case C-20240326-001 --section visual
# visual diff 경로, SSIM, mismatch regions 출력

ddk report --case C-20240326-001 --section fix-history
# 각 fix attempt의 hypothesis, changed files, validation delta 출력
```

---

### `ddk benchmark`

현재 케이스의 scorecard를 산출하고, baseline과 비교한다.

```
ddk benchmark [OPTIONS]

Options:
  --case TEXT           [필수] 케이스 ID
  --baseline PATH       기준 scorecard JSON (기본: benchmarks/gsd-baseline.json)
  --save                현재 run을 baseline으로 저장
  --json                JSON 형식 출력
```

**예:**
```bash
ddk benchmark --case C-20240326-001

# 출력:
# Scorecard — C-20240326-001
# ──────────────────────────────────────
# Precision:       8.2  (baseline: 7.5  ↑ +0.7)
# Maintainability: 7.8  (baseline: 7.0  ↑ +0.8)
# Automation:      8.5  (baseline: 6.5  ↑ +2.0)
# Scalability:     6.0  (reference only in v1)
# Composite:       8.2  (baseline: 7.0  ↑ +1.2) ✓ 8.5 target: not yet
# ──────────────────────────────────────
# Baseline: benchmarks/gsd-baseline.json (2024-03-20)
# Category: image-driven UI/code generation + verification loop
```

> ⚠️ `benchmarks/gsd-baseline.json` 이 없으면 comparative claim은 비활성화되고 절대 점수만 출력됩니다.

---

### `ddk cases`

이전 케이스 목록을 조회한다.

```
ddk cases [OPTIONS]

Options:
  --limit INT           출력 개수 (기본: 20)
  --status TEXT         필터 (ready | blocked | manual-review | all)
  --json                JSON 형식 출력
```

**예:**
```bash
ddk cases --limit 5

# C-20240326-003  ready           2024-03-26 14:20  dashboard-v2.png
# C-20240326-002  blocked         2024-03-26 13:10  login-page.png
# C-20240326-001  manual-review   2024-03-26 12:05  login-v3.png
```

---

## 8. 전체 파이프라인 예제

### 예제 1 — 대시보드 페이지 생성 (성공 케이스)

```bash
# 0. 환경 확인
ddk preflight

# 1. 전체 파이프라인 실행
ddk run \
  --image ./mockups/dashboard.png \
  --prompt "Analytics dashboard. Left sidebar with nav items, top header with user avatar,
            main content with 4 KPI cards (users, revenue, sessions, conversion),
            line chart below, recent activity table at bottom." \
  --repo /path/to/my-app

# 결과: READY ✅
# 생성 파일:
#   src/pages/DashboardPage.tsx
#   src/components/KPICard.tsx
#   src/components/ActivityTable.tsx
```

---

### 예제 2 — 실패 후 수동 개입 (manual-review 케이스)

```bash
# 파이프라인 실행
ddk run --image ./mockups/complex-form.png --prompt "..." --repo .
# → auto-fix exhausted, Decision: MANUAL-REVIEW

# 실패 상세 확인
ddk report --case C-20240326-002 --section visual
# → diff.png 확인

# 파일 되돌리기
ddk rollback --case C-20240326-002 --to 0

# 프롬프트를 보강하고 재시도
ddk run \
  --image ./mockups/complex-form.png \
  --prompt "기존 프롬프트 + 'FormField 컴포넌트는 src/components/FormField.tsx를 재사용할 것'" \
  --repo .
```

---

### 예제 3 — 단계별 실행 (디버깅)

```bash
# 단계 1: 입력 저장
ddk ingest --image ./ui.png --prompt "..." --repo . --case-id debug-001

# 단계 2: repo scan 결과 확인
ddk analyze --case debug-001
cat .ddk/cases/debug-001/repo-profile.json | jq '.design_tokens'

# 단계 3: intent 확인 후 생성
cat .ddk/cases/debug-001/intent-graph.json | jq '.unresolved_items'
# unresolved가 많으면 프롬프트 보완 후 re-analyze 가능

# 단계 4~8 순서 실행
ddk generate --case debug-001
ddk normalize --case debug-001
ddk validate --case debug-001 --checks build,typecheck
ddk visual-check --case debug-001
ddk certify --case debug-001
```

---

### 예제 4 — CI/CD 파이프라인 통합

```yaml
# .github/workflows/ddk-generate.yml
name: ddk generate

on:
  workflow_dispatch:
    inputs:
      image_path:
        description: 'Path to reference image'
        required: true
      prompt:
        description: 'Generation prompt'
        required: true

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install ddalggak
      - run: playwright install chromium
      - run: |
          ddk run \
            --image "${{ inputs.image_path }}" \
            --prompt "${{ inputs.prompt }}" \
            --repo . \
            --skip-preflight \
            --json > ddk-result.json
      - run: |
          STATUS=$(jq -r '.decision.status' ddk-result.json)
          echo "Decision: $STATUS"
          if [ "$STATUS" != "ready" ]; then exit 1; fi
      - uses: actions/upload-artifact@v4
        with:
          name: ddk-evidence-pack
          path: .ddk/cases/
    env:
      DDK_LLM_API_KEY: ${{ secrets.DDK_LLM_API_KEY }}
```

---

## 9. 출력 아티팩트 가이드

각 케이스는 `.ddk/cases/{case_id}/` 아래에 다음 파일을 생성한다.

```
.ddk/cases/C-20240326-001/
├── input.json                    # CaseInput: 사용자 입력 원본
├── repo-profile.json             # RepoProfile: repo 관례, tokens, layout
├── intent-graph.json             # IntentGraph: layout regions, confidence
├── generation-plan.json          # GenerationPlan: nodes, dependencies
├── generated-artifact.json       # GeneratedArtifactSet: 생성 파일 목록
├── normalization-report.json     # NormalizationReport: convention fixes
├── runtime-validation-report.json # RuntimeValidationReport: build/lint/runtime
├── visual-regression-report.json # VisualRegressionReport: SSIM, diff score
├── fix-attempts.json             # FixAttempt[]: 각 시도 history
├── scorecard.json                # Scorecard: precision/maintainability 등
├── release-decision.json         # ReleaseDecision: status, blockers
├── llm-call-records.json         # LLMCallRecord[]: model/seed/token 기록
├── screenshots/
│   ├── reference.png             # 입력 레퍼런스 이미지
│   ├── current.png               # 생성된 화면 스크린샷
│   └── diff.png                  # 시각적 diff (mismatch 강조)
└── evidence-pack/
    └── README.md                 # 이 케이스의 replay 방법 안내
```

### 주요 artifact 스키마

**`release-decision.json`**
```json
{
  "case_id": "C-20240326-001",
  "status": "ready",
  "blockers": [],
  "runtime_validation": "pass",
  "visual_regression": "pass",
  "auto_fix_attempts": 2,
  "scorecard_composite": 8.2,
  "timestamp": "2024-03-26T12:15:00Z"
}
```

**`visual-regression-report.json`**
```json
{
  "ssim": 0.94,
  "changed_pixel_ratio": 0.032,
  "critical_region_overlap": 0.96,
  "missing_critical_regions": [],
  "mismatch_regions": [],
  "verdict": "pass",
  "reference_path": "screenshots/reference.png",
  "current_path": "screenshots/current.png",
  "diff_path": "screenshots/diff.png"
}
```

**`fix-attempts.json`**
```json
[
  {
    "attempt_no": 1,
    "checkpoint_ref": "ddk/fix/C-20240326-001/attempt-1",
    "failure_classes": ["TYPE_ERROR"],
    "hypothesis": "Type mismatch on line 28: string vs number",
    "changed_files": ["src/pages/Login.tsx"],
    "validation_delta": {
      "before": { "typecheck": "fail" },
      "after": { "typecheck": "pass" }
    }
  }
]
```

---

## 10. 설정 파일 상세

### `.ddk/config.json` 전체 옵션

```json
{
  "project": {
    "name": "my-app",
    "repo_path": ".",
    "framework": "react-vite-typescript"
  },
  "llm": {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet",
    "fast_model": "claude-haiku",
    "temperature": 0.2,
    "seed": null
  },
  "sandbox": {
    "mode": "git-worktree",
    "network": "deny",
    "allowed_commands": [
      "npm run build",
      "npm run typecheck",
      "npm run lint",
      "npm test"
    ],
    "timeout_seconds": 120
  },
  "visual": {
    "viewport": { "width": 1440, "height": 900 },
    "browser": "chromium",
    "thresholds": {
      "ssim": 0.92,
      "changed_pixel_ratio": 0.05,
      "critical_region_overlap": 0.90,
      "missing_critical_regions": 0
    }
  },
  "auto_fix": {
    "max_retries": 3,
    "non_improving_detection": true
  },
  "cost": {
    "max_cost_per_case_usd": null,
    "warn_cost_per_case_usd": 1.0
  }
}
```

### `benchmarks/gsd-baseline.json` 구조

```json
{
  "baseline_id": "gsd-2024-03-20",
  "measured_at": "2024-03-20T10:00:00Z",
  "harness": "ddk-benchmark-v1",
  "category": "image-driven-ui-code-generation",
  "scores": {
    "precision": 7.5,
    "maintainability": 7.0,
    "automation": 6.5,
    "composite": 7.0
  },
  "test_cases": 10,
  "notes": "GSD baseline measured on same 10 React/Vite fixture cases"
}
```

---

## 11. 롤백 및 복구

### 언제 롤백이 필요한가

| 상황 | 권장 액션 |
|---|---|
| auto-fix exhausted → `manual-review` | `ddk rollback --case <id> --to 0` |
| auto-fix 후 코드가 이전보다 나빠진 경우 | `ddk rollback --case <id> --to <n>` |
| 생성 자체를 취소하고 싶은 경우 | `ddk rollback --case <id> --to 0` |

### 롤백 원리

딸깍은 auto-fix 시도 시작 전마다 git ref를 생성한다.

```
attempt-0  ←  pre-fix state (생성+normalize 후, fix 전)
attempt-1  ←  fix 1회 시도 전 상태
attempt-2  ←  fix 2회 시도 전 상태
attempt-3  ←  fix 3회 시도 전 상태
```

`ddk rollback --to 0` 은 attempt-0으로 완전 복원하므로, git working tree가 clean해진다.

### 수동 롤백

```bash
# ddk rollback 명령 없이 직접 git으로도 가능
git stash list | grep "ddk/fix/C-20240326-001"
git checkout ddk/fix/C-20240326-001/attempt-0 -- src/
```

---

## 12. 벤치마크 및 스코어카드

### Scorecard 점수 의미

| 축 | 설명 | 현재 P0 목표 |
|---|---|---|
| Precision | intent와 생성 결과의 일치율 | 8.5+ |
| Maintainability | repo convention alignment | 8.5+ |
| Automation | closed-loop 성공률 | 8.8+ |
| Scalability | v1 core 외 확장 가능성 | reference only |
| Composite | 가중 평균 | 8.5+ (특정 category) |

### GSD Baseline 비교

```bash
# baseline 없을 때
ddk benchmark --case C-20240326-001
# ⚠ benchmarks/gsd-baseline.json not found.
# Running in absolute-score-only mode. No comparative claims.

# baseline 있을 때
ddk benchmark --case C-20240326-001 --baseline benchmarks/gsd-baseline.json
# Precision:  8.2 (baseline: 7.5 ↑ +0.7)
```

> **중요**: comparative score가 GSD baseline을 초과해도, 비교 영역은 **image-driven UI generation + verification loop** 로 한정한다. GSD 전체 기능과의 비교가 아니다.

---

## 13. 고급 사용법

### 13.1 Viewport 프로파일별 Visual Check

```bash
ddk visual-check --case C-001 --viewport 375x812  # 모바일
ddk visual-check --case C-001 --viewport 768x1024  # 태블릿
ddk visual-check --case C-001 --viewport 1440x900  # 데스크탑
```

### 13.2 특정 failure class만 수정

```bash
ddk auto-fix --case C-001 --fix-type type       # type error만 수정
ddk auto-fix --case C-001 --fix-type visual     # visual mismatch만 수정
ddk auto-fix --case C-001 --fix-type build,lint # build + lint만 수정
```

### 13.3 JSON 출력으로 파이프라인 통합

```bash
ddk run --image ./ui.png --prompt "..." --repo . --json | jq '.decision.status'
ddk certify --case C-001 --json | jq '.blockers'
```

### 13.4 LLM Call 기록 확인 (reproducibility 검증)

```bash
cat .ddk/cases/C-001/llm-call-records.json | jq '.[] | {stage, model, temperature, input_tokens, output_tokens}'
```

### 13.5 Visual Threshold 직접 지정 (calibration)

```bash
ddk visual-check --case C-001 \
  --threshold '{"ssim": 0.90, "changed_pixel_ratio": 0.07}'
```

---

## 14. 트러블슈팅

### `ddk: command not found`

```bash
uv run ddk --help   # uv 환경에서 실행
# 또는
source .venv/bin/activate && ddk --help
```

### Playwright 오류

```bash
# Chromium 재설치
uv run playwright install chromium --with-deps

# 헤드리스 실패 시
ddk visual-check --case C-001 --headed  # 브라우저 표시
```

### Build tool not found

```bash
# Node.js 버전 확인
node --version  # 20+ 필요
nvm use 20      # nvm 사용 시
```

### LLM API 오류

```bash
# 키 설정 확인
echo $DDK_LLM_API_KEY

# 다른 모델로 재시도
DDK_LLM_MODEL=claude-3-haiku ddk run ...
```

### Visual check SSIM too low

원인 분류:

| 원인 | 해결 방법 |
|---|---|
| 레퍼런스 이미지 해상도 불일치 | `--viewport` 맞추기 |
| 폰트 로딩 지연 | `--visual-wait 2000` (ms) 옵션 |
| 다크모드/라이트모드 불일치 | `--theme light/dark` 옵션 |
| 프롬프트가 레이아웃을 잘못 서술 | 프롬프트 보완 후 재시도 |

### Manual review 상태 해결

```bash
# 1. 실패 내용 확인
ddk report --case C-001 --section visual
ddk report --case C-001 --section fix-history

# 2. pre-fix 상태로 복원
ddk rollback --case C-001 --to 0

# 3. 프롬프트 보강 후 재실행
ddk run --image ./ui.png --prompt "[더 구체적인 프롬프트]" --repo .
```

---

## 15. 용어 사전

| 용어 | 설명 |
|---|---|
| Case | 딸깍 실행 단위. `ddk ingest` 시 생성. `.ddk/cases/{id}/` 에 저장 |
| Preflight | 실행 전 환경 검사. 실패 시 실행 불가 |
| Evidence Pack | 한 케이스의 모든 artifact 모음 |
| Release Decision | `ready / blocked / manual-review` 최종 판정 |
| Checkpoint | auto-fix 시도 전 저장한 git ref. `ddk rollback` 의 복원 지점 |
| Failure Taxonomy | `TYPE_ERROR / BUILD_ERROR / LINT_ERROR / RUNTIME_ERROR / VISUAL_MISMATCH / CONSOLE_ERROR` 분류 |
| SSIM | 두 이미지의 구조적 유사도. 1.0에 가까울수록 유사 |
| Critical Region | CTA, 헤더, 핵심 폼 등 시각 회귀 시 반드시 보존해야 할 영역 |
| Context Pack | 각 LLM 호출에 전달되는 budgeted, structured context |
| Sandbox | generated code를 실행하는 격리 환경 (ephemeral git worktree 또는 container) |
| Non-improving Detection | auto-fix 루프에서 같은 실패 패턴이 반복될 때 조기 종료하는 메커니즘 |
| GSD Baseline | 비교 기준이 되는 GSD 측정 scorecard. 없으면 comparative claim 비활성화 |

---

> **참고**: 이 문서는 `docs/design/`의 설계 명세를 기반으로 작성된 사용자 인터페이스 명세입니다. 실제 구현 시 세부 flag 이름이나 출력 형식은 변경될 수 있습니다.

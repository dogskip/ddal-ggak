# 멀티툴 어댑터 설계 — 딸깍 Multi-tool Integration

## 1. 설계 원칙

딸깍은 **Claude Code, Gemini CLI, GitHub Copilot, OpenCode, Codex** 모든 AI 코딩 도구에서 동작해야 한다.

### 핵심 원칙

```
[AI 도구 X] → [Tool Adapter Layer] → [ddk CLI / MCP Server] → [딸깍 Core Engine]
```

- **Core Layer** (`ddk` Python CLI): 모든 도구에서 동일하게 실행됨. 도구-독립적.
- **Adapter Layer**: 각 도구에 맞는 얇은 wrapper (커맨드 파일, extension JSON, instructions).
- **MCP Layer**: MCP 지원 도구 (Claude Code, Copilot, OpenCode, Gemini CLI)는 `ddk mcp` 서버로 통합.

### 지원 레벨 정의

| 레벨 | 설명 |
|------|------|
| **L1 Full** | 모든 커맨드 + MCP + 자동 컨텍스트 주입 |
| **L2 Guided** | 슬래시커맨드 + subprocess ddk 실행 |
| **L3 Manual** | instructions.md 기반, 직접 ddk 호출 |

### Canonical Command Contract (SSoT)

멀티툴 adapter의 authoritative command surface는 `14-cli-spec.md` 이다.

- canonical CLI: `ddk preflight`, `ingest`, `analyze`, `plan`, `generate`, `validate`, `visual-check`, `fix`, `certify`, `rollback`, `run`, `design`, `install`, `mcp`, `status`, `init`
- wrapper alias: `/딸깍:설계`, `/ddk:run`, `@ddalggak ddk_run` 같은 도구별 진입점
- 규칙: wrapper는 반드시 **canonical CLI 또는 `ddk mcp` tool contract** 로 귀결되어야 한다.

고빈도 wrapper는 다음 8개를 권장한다.

| wrapper 목적 | canonical command |
|-------------|-------------------|
| 환경 점검 | `ddk preflight` |
| 초기 설정 | `ddk init` |
| 설계 문서 생성 | `ddk design` |
| 파이프라인 실행 | `ddk run` |
| 실행 검증 | `ddk validate` |
| visual gate | `ddk visual-check` |
| 상태 조회 | `ddk status` |
| 복구 | `ddk rollback` |

MCP server는 case-oriented tool만 노출한다.

`ddk_ingest`, `ddk_analyze`, `ddk_plan`, `ddk_generate`, `ddk_validate`, `ddk_visual_check`, `ddk_fix`, `ddk_certify`, `ddk_run`, `ddk_rollback`, `ddk_status`

---

## 2. 지원 도구별 통합 방식

| 도구 | 레벨 | 진입점 | 파일 위치 | 프로토콜 |
|------|------|--------|-----------|----------|
| Claude Code | **L1 Full** | `.claude/commands/ddk/` | 커맨드 `.md` 파일 | subprocess + MCP |
| GitHub Copilot | **L1 Full** | `.github/skills/ddalggak-*/` | skill `.md` 파일 | subprocess + MCP |
| Gemini CLI | **L2 Guided** | `.gemini/extensions/ddalggak/` | `extension.json` | subprocess |
| OpenCode | **L2 Guided** | `opencode.json` | MCP server 등록 | MCP |
| Codex (OpenAI) | **L3 Manual** | `.codex/instructions.md` | instructions | subprocess |

---

## 3. Claude Code Adapter (L1 Full)

### 파일 구조

```
.claude/
  commands/
    ddk/
      preflight.md           → /project:ddk/preflight
      init.md                → /project:ddk/init
      design.md              → /project:ddk/design
      run.md                 → /project:ddk/run
      validate.md            → /project:ddk/validate
      visual-check.md        → /project:ddk/visual-check
      status.md              → /project:ddk/status
      rollback.md            → /project:ddk/rollback
```

고급 분해 실행(`ingest`, `analyze`, `plan`, `generate`, `fix`, `certify`)은 wrapper 파일 대신 MCP tool 또는 직접 CLI 호출로 처리한다.

### 커맨드 파일 형식 (예: `design.md`)

```markdown
# 딸깍:설계 — 세계표준 설계 문서 자동 생성

주어진 아이디어로 세계/업계/한국 표준을 준수하는 10개 설계 문서 패키지를 생성한다.

## 실행

!ddk design "$ARGUMENTS"

## 동작

1. 인터뷰 모드로 요구사항 수렴
2. 10개 설계 문서 자동 생성 (SRS, PRD, Architecture, API, DB, Security, ADR, Test, Plan, AI Handoff)
3. 품질 점수 산출 및 보완 권고

## 예시

- /project:ddk/design "배달 앱 만들고 싶어"
- /project:ddk/design "결제 모듈 추가" --repo ./my-app
- /project:ddk/design "민원 처리 시스템" --standard egov
```

### MCP Server (`.mcp.json`)

```json
{
  "mcpServers": {
    "ddalggak": {
      "command": "ddk",
      "args": ["mcp", "--transport", "stdio"],
      "env": {
        "DDK_LLM_API_KEY": "${DDK_LLM_API_KEY}"
      }
    }
  }
}
```

MCP를 통해 딸깍의 모든 tool이 Claude Code의 tool-use API로 노출됨.

---

## 4. GitHub Copilot Adapter (L1 Full)

GSD와 동일한 파일 구조 패턴을 사용한다.

### 파일 구조

```
.github/
  skills/
    ddalggak-design/
      skill.md               ← /ddk:design 실행 정의
    ddalggak-init/
      skill.md
    ddalggak-run/
      skill.md
    ddalggak-validate/
      skill.md
    ddalggak-visual-check/
      skill.md
    ddalggak-status/
      skill.md
    ddalggak-rollback/
      skill.md
    ddalggak-preflight/
      skill.md
    ddalggak-install/
      skill.md
  agents/
    ddalggak-designer.md     ← 설계 문서 생성 에이전트
    ddalggak-executor.md     ← 코드 실행/검증 에이전트
    ddalggak-validator.md    ← 실행/시각 검증 에이전트
    ddalggak-recovery.md     ← rollback/복구 에이전트
```

### Skill 파일 형식 (예: `ddalggak-design/skill.md`)

```markdown
---
description: "딸깍:설계 — 아이디어를 세계표준 설계 문서 10개로 자동 변환"
---

# 딸깍:설계

주어진 아이디어나 요구사항으로 IEEE 830, ISO 42010, OpenAPI 3.0, ISMS-P 등
국제/업계/한국 표준을 준수하는 10개 설계 문서 패키지를 자동 생성한다.

## 실행 방법

`ddk design "$ARGUMENTS"` 를 실행한다.

## 생성 문서

1. SRS (IEEE 830 / TTA.KO 표준)
2. PRD (Amazon PR-FAQ 스타일)
3. Architecture (C4 Model / ISO 42010)
4. API Spec (OpenAPI 3.0)
5. DB Schema (ERD + 정규화)
6. Security Design (ISMS-P / OWASP Top 10)
7. ADR Set
8. Test Strategy (TDD 포함)
9. Implementation Plan (DORA 기준)
10. AI Handoff Package
```

### Agent 파일 형식 (예: `ddalggak-executor.md`)

```markdown
---
description: "딸깍 실행 에이전트 — Phase 실행, 검증, 자동수정 루프 담당"
allowed-tools: bash, glob, grep, view, edit, create
---

# 딸깍 실행 에이전트

이 에이전트는 딸깍의 실행 루프를 담당한다.
ingest → analyze → plan → generate → normalize → validate → visual-check → fix → certify

## 핵심 책임

1. `ddk run` 또는 분해 실행(`ingest/analyze/plan/generate/...`) 호출
2. 검증 실패 시 `ddk fix` 또는 MCP `ddk_fix` 호출
3. bounded retry 초과 시 `ddk rollback` 실행
4. evidence pack 생성 및 보고
```

### MCP 등록 (`~/.copilot/mcp.json` 또는 프로젝트 `.mcp.json`)

```json
{
  "mcpServers": {
    "ddalggak": {
      "command": "ddk",
      "args": ["mcp"]
    }
  }
}
```

---

## 5. Gemini CLI Adapter (L2 Guided)

### 파일 구조

```
.gemini/
  extensions/
    ddalggak/
      extension.json         ← 도구 정의
      README.md              ← 사용 설명
```

### `extension.json` 형식

```json
{
  "name": "ddalggak",
  "version": "1.0.0",
  "description": "딸깍 — 설계, 실행, 검증, 복구를 canonical ddk CLI로 연결하는 guided workflow.",
  "tools": [
    {
      "name": "ddk_preflight",
      "description": "환경 점검 및 remediation hint 출력",
      "type": "shell",
      "command": "ddk preflight",
      "parameters": { "type": "object", "properties": {} }
    },
    {
      "name": "ddk_init",
      "description": "워크스페이스 초기 설정 (Setup Wizard)",
      "type": "shell",
      "command": "ddk init",
      "parameters": {
        "type": "object",
        "properties": {
          "repo": { "type": "string", "description": "대상 repo 경로" },
          "adapter": { "type": "string", "enum": ["claude", "copilot", "gemini", "opencode", "codex", "all"] }
        }
      }
    },
    {
      "name": "ddk_design",
      "description": "아이디어를 세계표준 설계 문서 10개로 자동 생성 (IEEE 830, C4, OpenAPI, ISMS-P 등)",
      "type": "shell",
      "command": "ddk design",
      "parameters": {
        "type": "object",
        "properties": {
          "idea": {
            "type": "string",
            "description": "만들고 싶은 것에 대한 아이디어 또는 요구사항"
          },
          "standard": {
            "type": "string",
            "description": "적용할 표준: egov (전자정부), pci-dss, iso27001",
            "enum": ["egov", "pci-dss", "iso27001", "default"]
          },
          "repo": {
            "type": "string",
            "description": "기존 repo 경로 (새 기능 설계 시)"
          }
        },
        "required": ["idea"]
      }
    },
    {
      "name": "ddk_run",
      "description": "이미지/프롬프트/레포 기준 파이프라인 일괄 실행",
      "type": "shell",
      "command": "ddk run",
      "parameters": {
        "type": "object",
        "properties": {
          "image_paths": { "type": "array", "items": { "type": "string" }, "description": "입력 이미지 경로 목록" },
          "prompt": { "type": "string", "description": "생성 지시" },
          "repo": { "type": "string", "description": "대상 repo 경로" },
          "case_id": { "type": "string", "description": "케이스 ID (선택)" }
        },
        "required": ["image_paths", "prompt", "repo"]
      }
    },
    {
      "name": "ddk_validate",
      "description": "기존 case의 runtime validation 실행",
      "type": "shell",
      "command": "ddk validate",
      "parameters": {
        "type": "object",
        "properties": {
          "case_id": { "type": "string", "description": "검증할 케이스 ID" }
        },
        "required": ["case_id"]
      }
    },
    {
      "name": "ddk_visual_check",
      "description": "기존 case의 visual regression gate 실행",
      "type": "shell",
      "command": "ddk visual-check",
      "parameters": {
        "type": "object",
        "properties": {
          "case_id": { "type": "string", "description": "visual check를 실행할 케이스 ID" },
          "reference_path": { "type": "string", "description": "참조 이미지 경로 (선택)" }
        },
        "required": ["case_id"]
      }
    },
    {
      "name": "ddk_status",
      "description": "케이스 상태 및 artifact 진행 상황 조회",
      "type": "shell",
      "command": "ddk status",
      "parameters": {
        "type": "object",
        "properties": {
          "case_id": { "type": "string", "description": "조회할 케이스 ID" }
        },
        "required": ["case_id"]
      }
    },
    {
      "name": "ddk_rollback",
      "description": "자동 checkpoint로 되돌리기",
      "type": "shell",
      "command": "ddk rollback",
      "parameters": {
        "type": "object",
        "properties": {
          "target": { "type": "string", "description": "되돌릴 대상 (phase N, case C-001 등)" }
        }
      }
    },
    {
      "name": "ddk_install",
      "description": "AI 도구 어댑터 설치 — .claude/commands, .github/skills, .gemini/extensions 등 설치",
      "type": "shell",
      "command": "ddk install",
      "parameters": {
        "type": "object",
        "properties": {
          "adapter": {
            "type": "string",
            "description": "설치할 어댑터 이름",
            "enum": ["claude", "copilot", "gemini", "opencode", "codex", "all"]
          }
        },
        "required": ["adapter"]
      }
    }
  ]
}
```

### Gemini CLI에서 사용 방법

```
# extension 로드 후
@ddalggak ddk_preflight
@ddalggak ddk_init repo="."
@ddalggak ddk_design "배달 앱 만들고 싶어"
@ddalggak ddk_run image_paths=["./ref.png"] prompt="로그인 폼" repo="."
@ddalggak ddk_status case_id="C-001"
```

---

## 6. OpenCode Adapter (L2 Guided)

### `opencode.json` 설정

```json
{
  "mcpServers": {
    "ddalggak": {
      "command": "ddk",
      "args": ["mcp", "--transport", "stdio"],
      "env": {
        "DDK_LLM_API_KEY": "${DDK_LLM_API_KEY}"
      }
    }
  },
  "instructions": "이 프로젝트에서 AI 코딩 작업은 딸깍(ddk) 워크플로우를 사용한다. 시작 전 ddk preflight를 실행하고, 설정이 없으면 ddk init을 먼저 수행한다. 일반 작업은 ddk design 또는 ddk run을 사용하고, 필요 시 ddk validate, ddk visual-check, ddk status, ddk rollback으로 후속 조치한다."
}
```

### MCP Tool 목록 (ddk mcp 서버가 노출하는 도구)

```
ddk_ingest              — 케이스 생성
ddk_analyze             — 입력/레포 분석
ddk_plan                — 생성 계획 수립
ddk_generate            — 코드 생성
ddk_validate            — runtime validation
ddk_visual_check        — visual regression
ddk_fix                 — bounded auto-fix
ddk_certify             — 릴리즈 판정
ddk_run                 — end-to-end 파이프라인 실행
ddk_rollback            — checkpoint 복원
ddk_status              — 현재 상태
```

`design`, `init`, `install`, `preflight` 는 wrapper/CLI에서 직접 호출하고 MCP tool로는 노출하지 않는다.

---

## 7. Codex (OpenAI) Adapter (L3 Manual)

### `.codex/instructions.md` 형식

```markdown
# 딸깍(ddalggak) 워크플로우

이 프로젝트는 딸깍(ddk) 워크플로우를 사용한다.

## 작업 시작 전

반드시 `ddk preflight` 로 환경을 먼저 점검한다.

## 새 기능 개발 순서

1. `ddk preflight` — 환경 점검
2. `ddk init` — 초기 설정 (필요 시)
3. `ddk design "요구사항"` — 설계 문서 생성 (설계 우선 작업)
4. `ddk run --image ... --prompt ... --repo .` — 파이프라인 실행
5. `ddk status --case-id C-001` — 상태 확인
6. `ddk validate --case-id C-001` / `ddk visual-check --case-id C-001` — 개별 게이트 재실행
7. `ddk certify --case-id C-001` — 최종 판정

## 버그 수정

`ddk validate --case-id C-001` 로 실패를 재현하고, 필요 시 `ddk fix --case-id C-001` 또는 MCP `ddk_fix` 로 bounded repair를 실행한다.

## 설계 문서 생성

`ddk design "만들고 싶은 것"` — 세계표준 설계 문서 10개 자동 생성

## UI 생성

`ddk run --image reference.png --prompt "설명" --repo .` — 스크린샷 → 코드 + visual 검증

## 롤백

`ddk rollback --case-id C-001 --list` — 복원 가능한 checkpoint 목록
`ddk rollback --case-id C-001 --to attempt-1` — 지정 checkpoint로 복원

## 주의

- 생성된 코드는 ddk validate가 통과하기 전 머지하지 않는다.
- fix는 최대 3회로 제한됨. 초과 시 `ddk rollback`.
- 모든 LLM 호출은 artifact에 기록되며 `ddk status --json` 또는 evidence pack에서 확인한다.
```

### 전역 설정 (`~/.codex/instructions.md` 에 추가)

```markdown
## 딸깍(ddalggak) 프로젝트

딸깍이 설치된 repo에서는 `ddk` CLI를 사용해 AI 코딩 워크플로우를 실행한다.
`ddk preflight`로 환경 점검 후 `ddk init`, `ddk design`, `ddk run` 순으로 사용한다.
```

---

## 8. MCP Server 설계 (`ddk mcp`)

### 목적

MCP(Model Context Protocol)를 지원하는 모든 AI 도구 (Claude Code, Copilot, OpenCode, Gemini CLI 일부)는 `ddk mcp` 서버 하나로 딸깍 기능 전체에 접근할 수 있다.

### 실행

```bash
ddk mcp                      # stdio transport (기본값)
# HTTP transport는 vNext 범위
```

### MCP Server 구조 (`ddk/mcp_server.py`)

```python
from mcp import FastMCP
from ddk.core import ...

mcp = FastMCP("ddalggak", version="1.0.0")

@mcp.tool()
async def ddk_ingest(image_paths: list[str], prompt: str, repo_path: str, case_id: str | None = None) -> str:
    """케이스 생성"""
    ...

@mcp.tool()
async def ddk_analyze(case_id: str) -> str:
    """입력/레포 분석"""
    ...

@mcp.tool()
async def ddk_plan(case_id: str) -> str:
    """생성 계획 수립"""
    ...

@mcp.tool()
async def ddk_generate(case_id: str) -> str:
    """코드 생성"""
    ...

@mcp.tool()
async def ddk_validate(case_id: str) -> str:
    """runtime validation"""
    ...

@mcp.tool()
async def ddk_visual_check(case_id: str, reference_path: str | None = None) -> str:
    """visual regression"""
    ...

@mcp.tool()
async def ddk_fix(case_id: str, max_retries: int = 3) -> str:
    """bounded auto-fix"""
    ...

@mcp.tool()
async def ddk_certify(case_id: str, apply: bool = False) -> str:
    """릴리즈 판정"""
    ...

@mcp.tool()
async def ddk_run(image_paths: list[str], prompt: str, repo_path: str, case_id: str | None = None) -> str:
    """end-to-end 파이프라인 실행"""
    ...

@mcp.tool()
async def ddk_rollback(case_id: str, to: str | None = None, list_checkpoints: bool = False) -> str:
    """checkpoint로 복원"""
    ...

@mcp.tool()
async def ddk_status(case_id: str) -> str:
    """케이스 상태 조회"""
    ...
```

### MCP Tool 반환 타입 및 에러 계약

모든 MCP tool은 **JSON 문자열**을 반환한다. 반환 구조는 2가지:

#### 성공 응답

```json
{
  "status": "success",
  "case_id": "C-001",
  "result": { ... },  // tool별 결과 (아래 표 참조)
  "elapsed_seconds": 12.3
}
```

#### 실패 응답

```json
{
  "status": "error",
  "case_id": "C-001",
  "error_code": "LLM_TIMEOUT",
  "error_message": "Primary LLM provider timed out after 120s",
  "error_category": "LLM",
  "recoverable": true,
  "suggestion": "ddk_fix 또는 재실행 권장"
}
```

#### Tool별 `result` 스키마

| Tool | result 필드 | Pydantic 모델 참조 |
|------|------------|-------------------|
| `ddk_ingest` | `{"case_id": str, "input_summary": str}` | `CaseInput` (12 §1) |
| `ddk_analyze` | `{"repo_profile": object, "intent_graph": object}` | `RepoProfile` (12 §4), `IntentGraph` (12 §5) |
| `ddk_plan` | `{"generation_plan": object, "node_count": int}` | `GenerationPlan` (12 §6) |
| `ddk_generate` | `{"artifact_set": object, "files_generated": int}` | `GeneratedArtifactSet` (12 §7) |
| `ddk_validate` | `{"validation_report": object, "overall_status": str}` | `RuntimeValidationReport` (12 §9) |
| `ddk_visual_check` | `{"visual_report": object, "ssim_score": float}` | `VisualRegressionReport` (12 §10) |
| `ddk_fix` | `{"fix_attempt": object, "improved": bool}` | `FixAttempt` (12 §11) |
| `ddk_certify` | `{"release_decision": object, "verdict": str}` | `ReleaseDecision` (12 §12) |
| `ddk_run` | `{"scorecard": object, "release_decision": object}` | `Scorecard` (12 §12), `ReleaseDecision` |
| `ddk_rollback` | `{"restored_ref": str, "files_restored": int}` | — |
| `ddk_status` | `{"current_node": str, "terminal_state": str\|null, "cost_usd": float}` | `GraphState` (12 §GraphState) |

#### 에러 코드 분류

| error_code | error_category | recoverable | 설명 |
|------------|---------------|-------------|------|
| `INPUT_INVALID` | INPUT | false | 잘못된 입력 (이미지 없음, repo 없음) |
| `PRECONDITION_FAILED` | INPUT | false | 선행 단계 미완료 (intent-graph 없이 generate 호출) |
| `LLM_TIMEOUT` | LLM | true | LLM 응답 시간 초과 |
| `LLM_RATE_LIMIT` | LLM | true | 429 Too Many Requests |
| `LLM_PROVIDER_EXHAUSTED` | LLM | false | Primary + Fallback 모두 실패 |
| `LLM_CONTENT_FILTER` | LLM | false | 컨텐츠 필터 차단 |
| `COST_CAP_EXCEEDED` | COST | false | 건당 비용 상한 초과 |
| `BUILD_FAILED` | VALIDATION | true | 빌드 실패 (auto-fix 가능) |
| `SANDBOX_VIOLATION` | SECURITY | false | 샌드박스 정책 위반 |
| `SANDBOX_TIMEOUT` | INFRA | true | 샌드박스 타임아웃 |
| `VISUAL_MISMATCH` | VISUAL | false | 시각 임계값 미달 |
| `ROLLBACK_FAILED` | INFRA | false | 롤백 실패 |
| `INTERNAL_ERROR` | FATAL | false | 예상치 못한 내부 오류 |

#### 에러 전파 원칙

1. **LLM 계층 → MCP 계층**: `LLMRetryableError` → 재시도 후 실패 시 `{"error_code": "LLM_TIMEOUT", "recoverable": true}`
2. **어댑터 계층 → MCP 계층**: `subprocess` 실패 → `{"error_code": "BUILD_FAILED", "recoverable": true}`  
3. **보안 계층 → MCP 계층**: `SecurityError` → `{"error_code": "SANDBOX_VIOLATION", "recoverable": false}`
4. **미분류 예외 → MCP 계층**: `Exception` → `{"error_code": "INTERNAL_ERROR", "recoverable": false}`

모든 에러 응답은 `LLMCallRecorder`에 기록되며, `EvidencePack`에 포함된다.

### MCP 의존성

```toml
# pyproject.toml
[project.dependencies]
mcp = ">=1.0.0"
```

---

## 9. 도구별 설치 방법

### 공통 (ddk CLI 설치)

```bash
# uv 사용 (권장)
uv tool install ddalggak

# pip 사용
pip install ddalggak

# 설치 확인
ddk --version
ddk preflight
```

### Claude Code 설정

```bash
# 프로젝트 루트에서
ddk install --adapter claude
# → .claude/commands/ddk/ 폴더와 커맨드 파일 자동 생성
# → .mcp.json에 ddalggak MCP server 등록

# 수동 설치
ddk install --adapter claude --mode manual
```

설치 후: `/project:ddk/preflight` 입력해서 확인.

### GitHub Copilot 설정

```bash
ddk install --adapter copilot
# → .github/skills/ddalggak-*/ 폴더 생성
# → .github/agents/ddalggak-*.md 생성
# → .mcp.json에 MCP server 등록
```

설치 후: `/ddk:preflight (딸깍:환경점검)` 입력해서 확인.

### Gemini CLI 설정

```bash
ddk install --adapter gemini
# → .gemini/extensions/ddalggak/ 폴더 생성
# → extension.json 자동 생성
```

설치 후: `@ddalggak ddk_preflight` 입력해서 확인.

### OpenCode 설정

```bash
ddk install --adapter opencode
# → opencode.json에 ddalggak MCP server 등록
```

설치 후: `ddk mcp` 서버 실행 후 확인.

### Codex 설정

```bash
ddk install --adapter codex
# → .codex/instructions.md 생성
```

### 모든 도구 동시 설치

```bash
ddk install --adapter all
# Claude, Copilot, Gemini, OpenCode, Codex 모두 설치
```

---

## 10. 커맨드 호환성 매트릭스

| 커맨드 | Claude Code | Copilot | Gemini CLI | OpenCode | Codex |
|--------|-------------|---------|------------|----------|-------|
| `/ddk:preflight` | ✅ `/project:ddk/preflight` | ✅ skill | ✅ `@ddalggak ddk_preflight` | ⚠️ CLI wrapper | ⚠️ 수동 |
| `/ddk:init` | ✅ | ✅ | ✅ | ⚠️ CLI wrapper | ⚠️ |
| `/ddk:design` | ✅ `/project:ddk/design` | ✅ skill | ✅ `@ddalggak ddk_design` | ⚠️ CLI wrapper | ⚠️ |
| `/ddk:run` | ✅ `/project:ddk/run` | ✅ skill | ✅ `@ddalggak ddk_run` | ✅ MCP `ddk_run` | ⚠️ |
| `/ddk:validate` | ✅ | ✅ | ✅ | ✅ MCP `ddk_validate` | ⚠️ |
| `/ddk:visual-check` | ✅ | ✅ | ✅ | ✅ MCP `ddk_visual_check` | ⚠️ |
| `/ddk:status` | ✅ | ✅ | ✅ | ✅ MCP `ddk_status` | ⚠️ |
| `/ddk:rollback` | ✅ | ✅ | ✅ | ✅ MCP `ddk_rollback` | ⚠️ |

> ✅ Native support  ⚠️ Manual (`ddk 명령어` 직접 입력)

---

## 11. 도구별 호출 예시 비교

동일한 작업을 각 도구에서 실행하는 방법:

### 배달 앱 설계 문서 생성

```bash
# Claude Code
/project:ddk/design "배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"

# GitHub Copilot
/ddk:design (딸깍:설계) "배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"

# Gemini CLI
@ddalggak ddk_design idea="배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"

# OpenCode (MCP)
ddk design "배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"

# Codex (수동)
ddk design "배달 앱 만들고 싶어. 식당 목록, 주문, 실시간 추적"
```

### 파이프라인 실행

```bash
# Claude Code
/project:ddk/run --image ./ref.png --prompt "로그인 폼" --repo .

# GitHub Copilot
/ddk:run (딸깍:실행) --image ./ref.png --prompt "로그인 폼" --repo .

# Gemini CLI
@ddalggak ddk_run image_paths=["./ref.png"] prompt="로그인 폼" repo="."

# OpenCode
ddk_run(image_paths=["./ref.png"], prompt="로그인 폼", repo_path=".")

# Codex
ddk run --image ./ref.png --prompt "로그인 폼" --repo .
```

---

## 12. 설치 파일 디렉토리 전체 구조

```
프로젝트 루트/
├── .claude/
│   ├── commands/
│   │   └── ddk/
│   │       ├── preflight.md
│   │       ├── init.md
│   │       ├── design.md
│   │       ├── run.md
│   │       ├── validate.md
│   │       ├── visual-check.md
│   │       ├── status.md
│   │       ├── rollback.md
│   │       └── install.md
│   └── CLAUDE.md (딸깍 워크플로우 지침)
├── .mcp.json (Claude + Copilot MCP 설정)
├── .gemini/
│   └── extensions/
│       └── ddalggak/
│           ├── extension.json
│           └── README.md
├── .github/
│   ├── skills/
│   │   ├── ddalggak-design/skill.md
│   │   ├── ddalggak-init/skill.md
│   │   ├── ddalggak-run/skill.md
│   │   ├── ddalggak-validate/skill.md
│   │   ├── ddalggak-visual-check/skill.md
│   │   ├── ddalggak-status/skill.md
│   │   ├── ddalggak-rollback/skill.md
│   │   ├── ddalggak-preflight/skill.md
│   │   └── ddalggak-install/skill.md
│   └── agents/
│       ├── ddalggak-designer.md
│       ├── ddalggak-executor.md
│       ├── ddalggak-validator.md
│       └── ddalggak-recovery.md
├── opencode.json
└── .codex/
    └── instructions.md
```

---

## 13. 테스트 요구사항

### DDK-REQ-026 Multi-tool Adapter 검증

| 테스트 | 레벨 | 목적 |
|--------|------|------|
| `test_mcp_server_tools.py` | Contract | MCP tool 목록 + schema 검증 |
| `test_mcp_server_run.py` | Integration | `ddk_run` MCP call 성공 |
| `test_mcp_server_status.py` | Integration | `ddk_status` MCP call 성공 |
| `test_install_adapter_claude.py` | Integration | `ddk install --adapter claude` 파일 생성 검증 |
| `test_install_adapter_copilot.py` | Integration | `ddk install --adapter copilot` 파일 생성 검증 |
| `test_install_adapter_gemini.py` | Integration | `ddk install --adapter gemini` extension.json 검증 |
| `test_install_adapter_opencode.py` | Integration | `ddk install --adapter opencode` opencode.json 검증 |
| `test_install_adapter_codex.py` | Integration | `ddk install --adapter codex` instructions.md 검증 |
| `test_extension_json_schema.py` | Contract | Gemini extension.json 스키마 검증 |
| `test_claude_command_files.py` | Contract | `.claude/commands/ddk/*.md` 파일 형식 검증 |
| `test_github_skill_files.py` | Contract | `.github/skills/ddalggak-*/skill.md` 형식 검증 |

### TDD 모드

- MCP server tool schema: **TDD required**
- `ddk install` 파일 생성 로직: **TDD required**
- extension.json 생성 로직: **TDD required**
- claude commands 파일 생성: **TDD required**

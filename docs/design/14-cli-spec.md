# CLI 완전 명세

> 딸깍 CLI (`ddk`) 전체 서브커맨드 명세.
> 이 문서 없이는 CLI 구현자가 인자 타입, 기본값, 에러 코드를 추론해야 한다.

---

## 전역 옵션

```
ddk [GLOBAL_OPTIONS] <command> [COMMAND_OPTIONS]

Global Options:
  --case-dir PATH        .ddk/ 런타임 디렉토리 (기본값: {cwd}/.ddk)
  --log-level TEXT       DEBUG | INFO | WARNING | ERROR (기본값: INFO)
  --no-color             색상 비활성화
  --json-output          모든 출력을 JSON으로 (CI/CD용)
  --dry-run              실제 파일 변경 없이 계획만 출력
  --version              버전 출력 후 종료
  --help                 도움말
```

---

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `DDK_LLM_PROVIDER` | LLM 프로바이더 | `anthropic` |
| `DDK_ANTHROPIC_API_KEY` | Anthropic API 키 | (필수) |
| `DDK_OPENAI_API_KEY` | OpenAI API 키 (fallback) | (선택) |
| `DDK_LLM_MODEL` | 기본 모델 오버라이드 | `claude-3-5-sonnet-20241022` |
| `DDK_COST_CAP_USD` | 케이스당 비용 상한 | `2.0` |
| `DDK_SANDBOX_MODE` | `worktree` \| `docker` | `worktree` |
| `DDK_PLAYWRIGHT_BROWSER` | `chromium` \| `firefox` \| `webkit` | `chromium` |
| `DDK_LOG_LEVEL` | 로그 레벨 | `INFO` |
| `DDK_CASE_DIR` | 케이스 디렉토리 오버라이드 | `{cwd}/.ddk` |

---

## 1. `ddk preflight`

환경 요건을 사전 점검한다. 설치 후 최초 실행.

```
ddk preflight [--fix] [--verbose]

Options:
  --fix        자동 수정 가능한 항목은 자동 처리 (예: npm install playwright)
  --verbose    점검 상세 출력

검사 항목:
  ✓ Python >= 3.11
  ✓ uv 설치
  ✓ DDK_ANTHROPIC_API_KEY 설정
  ✓ Playwright 설치 (Chromium)
  ✓ Node.js / npm 설치 (대상 repo 빌드에 필요)
  ✓ git >= 2.30 (git worktree 지원)

종료 코드:
  0 = 모든 점검 통과
  1 = 치명적 실패 (API key 없음, Python 버전 부족 등)
  2 = 경고 (일부 선택적 항목 실패)

출력 예시 (--json-output):
  {
    "status": "pass"|"warn"|"fail",
    "items": [
      {"name": "python_version", "status": "pass", "detail": "3.12.0"},
      {"name": "anthropic_key", "status": "pass"},
      {"name": "playwright", "status": "warn", "detail": "not installed", "fix": "playwright install chromium"}
    ]
  }
```

---

## 2. `ddk ingest`

이미지와 입력을 케이스로 등록한다.

```
ddk ingest
  --image PATH...          [필수] 입력 이미지 (1~5개, PNG/JPEG/WEBP)
  --prompt TEXT            [필수] 생성 지시
  --repo PATH              [필수] 대상 repo 루트
  --case-id TEXT           케이스 ID (미지정 시 자동 생성: C-{datetime})
  --ref-image PATH...      시각 참조 이미지 (visual regression 기준)
  --notes TEXT             추가 컨텍스트

출력: case_id 출력
종료 코드:
  0 = 성공
  1 = 이미지 파일 없음
  2 = repo 경로 없음
  10 = 입력 검증 실패

예시:
  ddk ingest \
    --image mockups/dashboard.png \
    --prompt "사이드바와 차트를 포함한 대시보드 페이지 생성" \
    --repo /workspace/my-app \
    --case-id C-001
```

---

## 3. `ddk analyze`

등록된 케이스의 repo를 스캔하고 IntentGraph를 추출한다.

```
ddk analyze
  --case-id TEXT           [필수]
  --skip-repo-scan         repo 스캔 생략 (RepoProfile이 이미 있을 때)
  --model TEXT             사용할 모델 오버라이드

출력:
  - .ddk/cases/{case_id}/repo-profile.json
  - .ddk/cases/{case_id}/intent-graph.json
  - 요약 출력 (confidence, unresolved 항목 수)

종료 코드:
  0 = 성공
  1 = case_id 없음
  2 = 이미지 인코딩 실패
  3 = LLM 호출 실패
  4 = 비용 한도 초과
  20 = IntentGraph confidence < 0.5 (경고 포함 성공)

예시:
  ddk analyze --case-id C-001
```

---

## 4. `ddk plan`

IntentGraph에서 GenerationPlan을 생성한다.

```
ddk plan
  --case-id TEXT           [필수]
  --dry-run                계획만 출력, 저장 안 함

출력:
  - .ddk/cases/{case_id}/generation-plan.json
  - 노드 수, 대상 파일 목록 출력

종료 코드:
  0 = 성공
  1 = case_id 없음
  2 = intent-graph.json 없음
  3 = LLM 호출 실패

예시:
  ddk plan --case-id C-001 --dry-run
```

---

## 5. `ddk generate`

GenerationPlan에 따라 코드를 생성하고 정규화한다.

```
ddk generate
  --case-id TEXT           [필수]
  --skip-normalize         convention 정규화 생략
  --model TEXT             사용할 모델 오버라이드

출력:
  - .ddk/cases/{case_id}/generated-artifacts.json
  - .ddk/cases/{case_id}/normalization-report.json
  - 생성된 파일 목록 출력

종료 코드:
  0 = 성공
  1 = 선행 artifact 없음
  3 = LLM 호출 실패
  4 = 비용 한도 초과

예시:
  ddk generate --case-id C-001
```

---

## 6. `ddk validate`

생성된 코드를 sandbox에서 빌드/타입/lint/런타임 검증한다.

```
ddk validate
  --case-id TEXT           [필수]
  --apply                  검증 후 파일을 실제 repo에 적용 (기본: sandbox only)
  --timeout INT            전체 타임아웃 초 (기본: 120)

출력:
  - .ddk/cases/{case_id}/runtime-validation-report.json
  - 통과/실패 항목 출력

종료 코드:
  0 = 모두 통과
  1 = BUILD 실패
  2 = TYPE 실패
  3 = LINT 실패
  4 = RUNTIME 실패
  5 = VISUAL 실패
  10 = sandbox 초기화 실패

예시:
  ddk validate --case-id C-001
```

---

## 7. `ddk visual-check`

스크린샷 캡처 후 visual regression 검사를 실행한다.

```
ddk visual-check
  --case-id TEXT           [필수]
  --reference PATH         참조 이미지 오버라이드 (default: case의 ref-image)
  --viewport TEXT          "widthxheight" (기본: 1280x800)
  --browser TEXT           chromium | firefox | webkit (기본: chromium)
  --ssim-threshold FLOAT   SSIM 통과 기준 (기본: 0.92)
  --pixel-threshold FLOAT  pixel diff 비율 상한 (기본: 0.05)

출력:
  - .ddk/cases/{case_id}/screenshots/generated.png
  - .ddk/cases/{case_id}/screenshots/diff.png
  - .ddk/cases/{case_id}/visual-regression-report.json

종료 코드:
  0 = 통과
  1 = SSIM 기준 미달
  2 = critical region 누락
  3 = Playwright 실행 실패
  4 = 앱 부팅 실패

예시:
  ddk visual-check --case-id C-001 --ssim-threshold 0.90
```

---

## 8. `ddk fix`

실패 분류에 따라 자동 수정을 최대 N회 시도한다.

```
ddk fix
  --case-id TEXT           [필수]
  --max-retries INT        최대 재시도 횟수 (기본: 3)
  --target TEXT...         수정할 taxonomy ID (미지정 시 전체 실패 대상)
  --no-visual              visual regression 생략

출력:
  - .ddk/cases/{case_id}/fix-attempts.json (각 시도 appended)
  - 시도별 결과 (improved/no_change/regression/pass)

종료 코드:
  0 = 최종 통과
  1 = 최대 재시도 도달 (개선 없음)
  2 = regression 감지 (즉시 중단)
  3 = 선행 validation report 없음

예시:
  ddk fix --case-id C-001 --max-retries 3
```

---

## 9. `ddk certify`

모든 게이트 통과 후 Scorecard와 ReleaseDecision을 생성한다.

```
ddk certify
  --case-id TEXT           [필수]
  --baseline PATH          GSD baseline JSON 경로 (비교용)
  --apply                  certified-ready 시 파일을 실제 repo에 적용

출력:
  - .ddk/cases/{case_id}/scorecard.json
  - .ddk/cases/{case_id}/release-decision.json
  - .ddk/cases/{case_id}/evidence-pack.json
  - 최종 상태 출력: certified-ready | certified-blocked | manual-review-required

종료 코드:
  0 = certified-ready
  1 = certified-blocked
  2 = manual-review-required
  3 = 선행 artifact 미완성

예시:
  ddk certify --case-id C-001 --apply
```

---

## 10. `ddk rollback`

케이스 생성 이전 상태로 repo를 복원한다.

```
ddk rollback
  --case-id TEXT           [필수]
  --to-checkpoint TEXT     특정 체크포인트 ref (미지정 시 케이스 시작점)
  --confirm                확인 프롬프트 생략

출력:
  - 복원된 파일 목록

동작:
  1. .ddk/cases/{case_id}/checkpoint-pre-run.ref 에서 체크포인트 git ref 읽기
  2. git worktree를 해당 ref로 reset
  3. 변경된 파일을 repo에 복사 후 적용
  (실제로는 git checkout으로 원복)

종료 코드:
  0 = 성공
  1 = 체크포인트 없음
  2 = git 복원 실패

예시:
  ddk rollback --case-id C-001 --confirm
```

---

## 11. `ddk run` (파이프라인 단축 실행)

ingest → analyze → plan → generate → validate → visual-check → fix → certify를 한 번에 실행한다.

```
ddk run
  --image PATH...          [필수]
  --prompt TEXT            [필수]
  --repo PATH              [필수]
  --case-id TEXT           자동 생성 가능
  --ref-image PATH...      visual regression 참조 이미지
  --max-retries INT        auto-fix 최대 재시도 (기본: 3)
  --apply                  certified-ready 시 자동 적용
  --no-visual              visual regression 생략 (빠른 검증용)

출력:
  - 각 단계별 진행 상황
  - 최종: certified-ready | certified-blocked | manual-review-required
  - 소요 시간, 총 비용

종료 코드:
  ingest/analyze/plan/generate/validate/fix/certify 단계 코드 그대로 전파

예시:
  ddk run \
    --image mockups/login.png \
    --prompt "로그인 페이지 생성" \
    --repo /workspace/my-app \
    --apply
```

---

## 12. `ddk design`

사용자와 인터뷰하여 표준 설계 문서 세트를 생성한다.

```
ddk design
  --output-dir PATH        출력 디렉토리 (기본: docs/design/)
  --template TEXT          doc-set 템플릿 (기본: full | minimal | api-only)
  --interactive            인터뷰 모드 (기본: true)
  --batch FILE             인터뷰 응답 파일 (비대화형 CI용)

생성 파일:
  - 00-document-inventory.md
  - 27-identity-positioning.md
  - 02-prd.md
  - 03-constraints-nfr.md
  - 04-system-design.md
  - 05-adr-set.md
  - 06-tech-spec.md
  - 07-verification-release.md
  - 08-consistency-review.md
  - 09-ai-handoff.md

종료 코드:
  0 = 성공
  1 = 인터뷰 중단
  2 = 출력 디렉토리 권한 없음

예시:
  ddk design --output-dir docs/design/ --template full
```

---

## 13. `ddk install`

대상 AI 도구에 딸깍 통합을 설치한다.

```
ddk install
  --adapter TEXT           claude | copilot | gemini | opencode | codex | all
  --target PATH            설치 대상 repo (기본: cwd)
  --uninstall              설치 제거

동작:
  claude   → .claude/commands/ddk/*.md 생성
  copilot  → .github/skills/ddalggak-*/ 생성
  gemini   → .gemini/extensions/ddalggak/extension.json 생성
  opencode → opencode.json에 MCP server 등록
  codex    → .codex/instructions.md에 딸깍 지침 추가
  all      → 위 5개 모두

종료 코드:
  0 = 성공
  1 = 알 수 없는 adapter
  2 = 권한 없음

예시:
  ddk install --adapter all --target /workspace/my-app
  ddk install --adapter claude
```

---

## 14. `ddk mcp`

딸깍 MCP 서버를 stdio transport로 실행한다.

```
ddk mcp
  --transport TEXT         stdio (현재 지원: stdio만)
  --log-file PATH          MCP 서버 로그 파일

동작:
  FastMCP 기반 stdio server 실행.
  Claude Code, Copilot, OpenCode에서 .mcp.json으로 자동 연결.

MCP 노출 도구:
  - ddk_ingest(image_paths, prompt, repo_path, case_id?)
  - ddk_analyze(case_id)
  - ddk_plan(case_id)
  - ddk_generate(case_id)
  - ddk_validate(case_id)
  - ddk_visual_check(case_id, reference_path?)
  - ddk_fix(case_id, max_retries?)
  - ddk_certify(case_id, apply?)
  - ddk_run(image_paths, prompt, repo_path, ...)
  - ddk_rollback(case_id)
  - ddk_status(case_id)

예시:
  ddk mcp --transport stdio
```

---

## 15. `ddk status`

케이스의 현재 상태와 진행 상황을 출력한다.

```
ddk status
  --case-id TEXT           [필수]
  --all                    모든 케이스 목록
  --json                   JSON 출력

출력:
  Case C-001:
    Status: in-progress (validate)
    Created: 2024-12-01T10:00:00Z
    Duration: 3m 42s
    Cost: $0.42
    Fix Attempts: 1/3

종료 코드:
  0 = 성공
  1 = case_id 없음
```

---

## 에러 코드 전체 표

| 코드 | 범주 | 설명 |
|------|------|------|
| 0 | - | 성공 |
| 1 | INPUT | 입력 파일/경로 없음 |
| 2 | INPUT | 입력 검증 실패 |
| 3 | LLM | LLM 호출 실패 |
| 4 | COST | 비용 한도 초과 |
| 5 | VISUAL | visual regression 실패 |
| 10 | INFRA | sandbox/환경 초기화 실패 |
| 11 | INFRA | git 오류 |
| 12 | INFRA | Playwright 오류 |
| 20 | WARN | 경고 포함 성공 (낮은 confidence 등) |
| 30 | BLOCKED | 최대 재시도 도달 |
| 31 | BLOCKED | regression 감지 |
| 40 | MANUAL | manual-review-required |
| 99 | FATAL | 예기치 않은 오류 |

---

## 16. `ddk init` (Setup Wizard)

새 프로젝트에서 딸깍을 처음 설정할 때 사용하는 대화형 마법사.

```
ddk init
  --repo PATH              대상 repo (기본: cwd)
  --adapter TEXT           설치할 AI 도구 어댑터 (기본: claude)
  --non-interactive        응답 기본값 자동 수락 (CI용)

동작 순서:
  1. ddk preflight --fix     → 환경 요건 자동 수정
  2. ddk install --adapter X → AI 도구 어댑터 설치
  3. .ddk/config.json 초기화 → API key 입력 안내
  4. fixtures/repos/react-vite-ts/ 픽스처 다운로드 여부 확인
  5. ddk run --dry-run        → 설정 유효성 smoke check

출력:
  - .ddk/config.json 생성
  - 설치된 어댑터 목록
  - "ddk run --image ... --prompt ... --repo ." 사용 안내

종료 코드:
  0 = 초기화 성공
  1 = preflight 치명적 실패
  2 = API key 미입력

예시:
  ddk init                             # 대화형
  ddk init --adapter all --non-interactive  # CI/CD 환경
```

### `.ddk/config.json` 초기 구조

```json
{
  "schema_version": "1.0",
  "llm": {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "light_model": "claude-3-haiku-20240307",
    "cost_cap_usd": 2.0
  },
  "sandbox": {
    "mode": "worktree",
    "timeout_seconds": 300
  },
  "visual": {
    "browser": "chromium",
    "viewport": "1280x800",
    "ssim_threshold": 0.92,
    "pixel_diff_threshold": 0.05
  },
  "reproducibility": {
    "mode": "best_effort",
    "benchmark_seed": 42,
    "record_all_calls": true
  }
}
```

---

## CLI 구현 기술 선택

- **프레임워크**: [Typer](https://typer.tiangolo.com/) (Click 기반, Pydantic 친화적)
- **진행 상황**: Rich progress bar + live table
- **로깅**: structlog (JSON 모드 지원)
- **진입점**: `pyproject.toml` `[project.scripts]`에 `ddk = "ddk.cli:app"`

```python
# src/ddk/cli.py (구조 스케치)
import typer
from rich.console import Console
from . import __version__

app = typer.Typer(name="ddk", help="딸깍 — self-correcting UI generation loop")
console = Console()

@app.command()
def preflight(fix: bool = False, verbose: bool = False): ...

@app.command()
def ingest(
    image: list[Path] = typer.Option(..., "--image"),
    prompt: str = typer.Option(..., "--prompt"),
    repo: Path = typer.Option(..., "--repo"),
    case_id: str | None = typer.Option(None, "--case-id"),
): ...

# ... 나머지 서브커맨드
```

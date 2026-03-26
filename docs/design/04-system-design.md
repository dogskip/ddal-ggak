# 시스템 설계

## 1. 설계 목표

`딸깍`의 시스템 설계는 다음 목표를 가진다.

1. visual-first generation
2. repo-aware normalization
3. sandboxed runtime validation
4. visual regression gating
5. bounded self-healing
6. evidence-rich certification

즉 시스템 전체는 **generator** 가 아니라 **self-correcting production loop** 로 설계된다.

## 2. 6-Level Architecture (Multi-tool 포함)

### Level 0 — Multi-tool Entry Layer (신규)

딸깍은 Claude Code, GitHub Copilot, Gemini CLI, OpenCode, Codex 모든 AI 도구에서 동작한다.

| 도구 | 진입 방식 | 파일 위치 | 지원 레벨 |
|------|-----------|-----------|-----------|
| Claude Code | `/project:ddk/커맨드` | `.claude/commands/ddk/` | L1 Full (subprocess + MCP) |
| GitHub Copilot | `/ddk:커맨드 (딸깍:한국어)` | `.github/skills/ddalggak-*/` | L1 Full (subprocess + MCP) |
| Gemini CLI | `@ddalggak ddk_커맨드` | `.gemini/extensions/ddalggak/` | L2 Guided (subprocess) |
| OpenCode | MCP tool call | `opencode.json` | L2 Guided (MCP) |
| Codex | 직접 `ddk` 호출 | `.codex/instructions.md` | L3 Manual |

**핵심 원칙:** Core(`ddk` CLI)는 도구에 독립적이다. 각 도구는 얇은 adapter wrapper만 다를 뿐 동일한 딸깍 엔진을 실행한다.

**MCP Server 레이어:** `ddk mcp` 서버를 통해 MCP 지원 도구 (Claude Code, Copilot, OpenCode) 모두 단일 인터페이스로 딸깍에 접근한다.

```
ddk mcp --transport stdio   # Claude Code, Copilot, OpenCode 연결
ddk mcp --transport http    # HTTP 기반 연결
```

설치:
```bash
ddk install --adapter claude    # .claude/commands/ddk/ + .mcp.json
ddk install --adapter copilot   # .github/skills/ + .github/agents/
ddk install --adapter gemini    # .gemini/extensions/ddalggak/
ddk install --adapter opencode  # opencode.json MCP 등록
ddk install --adapter codex     # .codex/instructions.md
ddk install --adapter all       # 전체
```

> 상세 설계: [10-multi-tool-adapter.md](./10-multi-tool-adapter.md)

### Level 1 — Input & Interaction

- CLI entrypoint: `ddk`
- input: image(s), prompt, repo path, optional reference notes
- output: human summary, `--json`, evidence pack paths, diff report

### Level 2 — Orchestration State Machine

전체 흐름을 **LangGraph** state machine으로 관리한다.

- ingest
- repo_scan
- intent_extract
- plan
- generate
- normalize
- runtime_validate
- visual_regress
- auto_fix
- benchmark
- certify

### Level 3 — Domain Services

- `RepoConventionScanner`
- `SemanticIntentExtractor`
- `DesignSystemInferencer`
- `GenerationPlanner`
- `CodeGenerator`
- `OutputNormalizer`
- `RuntimeValidationAggregator`
- `VisualRegressionService`
- `FailureClassifier`
- `AutoFixPlanner`
- `RetryBudgetController`
- `ContextPackBuilder`
- `BenchmarkScorecardService`
- `ReleaseDecisionService`
- `EvidencePackBuilder`

### Level 4 — Adapters & Tooling

- LLM adapter
- filesystem adapter
- git adapter
- sandbox runner adapter
- build/test runner adapter
- Playwright browser adapter
- screenshot diff adapter
- console/network capture adapter

### Level 5 — Evidence & Persistence

- Pydantic JSON artifacts
- audit log
- runtime validation logs
- screenshot/diff artifacts
- fix attempt history
- benchmark scorecard
- release decision

## 3. 추천 구현 스택

| 영역 | 선택 |
| --- | --- |
| Language | Python 3.12+ |
| Package manager | `uv` |
| CLI | Typer |
| State models | Pydantic v2 |
| Graph orchestration | LangGraph |
| Static checks | Ruff + Pyright |
| Tests | pytest |
| Browser | Playwright Python |
| Diff | perceptual diff adapter |
| Sandbox | container 또는 ephemeral worktree + command allowlist |

## 4. 핵심 Pydantic 모델

| 모델 | 목적 | 핵심 필드 |
| --- | --- | --- |
| `CaseInput` | 사용자 입력 | image_paths, prompt, repo_path, reference_notes |
| `RepoProfile` | 저장소 관례 | framework, package_manager, naming_rules, file_layout, design_tokens |
| `IntentGraph` | semantic intent | layout_regions, components, interactions, confidence, unresolved_items |
| `GenerationPlan` | 생성 계획 | nodes, dependencies, target_files, validation_hooks |
| `GeneratedArtifactSet` | 생성 결과 | files, trace, changed_paths |
| `NormalizationReport` | 정규화 결과 | convention_fixes, unresolved_drift |
| `RuntimeValidationReport` | 실행 검증 결과 | build_status, type_status, lint_status, runtime_status, console_errors |
| `VisualRegressionReport` | 시각 검증 결과 | ssim, changed_pixel_ratio, mismatch_regions, critical_region_overlap |
| `FixAttempt` | 자동 수정 시도 | attempt_no, hypothesis, changed_files, validation_delta |
| `Scorecard` | 제품 점수 | precision, maintainability, automation, scalability, composite |
| `ReleaseDecision` | 최종 판정 | status, blockers, human_actions |

## 5. State Machine 흐름

```text
ingest
  -> repo_scan
  -> intent_extract
  -> plan
  -> generate
  -> normalize
  -> runtime_validate
  -> visual_regress
      -> if pass: benchmark
      -> if fail and retry_budget_left: auto_fix -> normalize -> runtime_validate -> visual_regress
      -> if fail and no_budget: manual_review
  -> certify
```

### Terminal States

- `certified-ready`
- `certified-blocked`
- `manual-review-required`
- `runtime-failed`
- `visual-mismatch-blocked`
- `fix-budget-exhausted`

## 6. Closed Loop 정의

`딸깍`의 최소 제품 루프는 다음 6단계다.

1. Generate
2. Normalize
3. Runtime Validate
4. Visual Regress
5. Auto-fix
6. Certify

이 중 하나라도 빠지면 `딸깍`은 product가 아니라 generator다.

## 7. LLM Context Injection Contract

LangGraph state를 저장하는 것만으로는 충분하지 않다. 각 LLM 호출은 명시적 **context pack** 을 받아야 한다.

### 7.1 Context Pack 원칙

- 필요한 정보만 전달
- 원문 전체보다 구조화 요약 우선
- retry 시 이전 실패 전체 로그 대신 압축 요약 전달
- budget 초과 시 오래된 보조 컨텍스트부터 제거

### 7.2 단계별 Context Pack

| 단계 | 필수 입력 | 압축 전략 | 초기 budget(assumption) |
| --- | --- | --- | --- |
| `intent_extract` | input summary, image metadata, repo summary | repo summary는 1페이지 요약만 유지 | 6k tokens |
| `generate` | intent graph, target file map, repo conventions, design tokens | relevant source는 최대 6 files / 300 lines | 12k tokens |
| `normalize` | generated diff, convention rules, canonical examples | changed files 중심만 전달 | 8k tokens |
| `auto_fix` | failure taxonomy, top errors, current diff, prior attempt summaries | prior attempts는 시도당 3 bullet 요약만 유지 | 10k tokens |

### 7.3 Retry Context Compaction

- retry 2: unchanged log lines 제거, delta만 유지
- retry 3: non-improving errors는 ID/hash만 유지
- budget 초과 시 `manual-review-required`

### 7.4 ContextPackBuilder 파일 선택 알고리즘

`generate` 노드는 repo에서 컨텍스트 파일을 최대 6개 / 300줄로 제한해 선택한다.

**파일 우선순위 (내림차순)**:

| 우선순위 | 선택 기준 | 예시 |
|---------|---------|------|
| P1 (필수) | IntentGraph에서 명시적으로 참조된 파일 | 컴포넌트 A가 re-export하는 index.ts |
| P2 (높음) | target_files의 동일 디렉토리에 있는 형제 파일 | Button.tsx 옆의 Input.tsx |
| P3 (중간) | RepoProfile.naming_rules의 canonical 예시 파일 | 공식 버튼 컴포넌트 예시 |
| P4 (낮음) | RepoProfile.design_tokens 소스 파일 | tokens.ts, theme.ts |
| P5 (배경) | 공유 타입 정의 파일 | types/index.ts |

**300줄 초과 시 트리밍**:
1. 파일을 우선순위 P1→P5 순으로 추가
2. 각 파일에서 `target_file과 직접 관련된 symbol 정의 근처 ±20줄` 만 포함
3. 나머지는 `// ... (N lines omitted)` placeholder로 교체

```python
# src/ddk/services/context_pack_builder.py (구현 계약)

class ContextPackBuilder:
    MAX_FILES = 6
    MAX_LINES = 300

    def build(
        self,
        intent_graph: IntentGraph,
        repo_profile: RepoProfile,
        target_files: list[str],
        repo_path: Path,
    ) -> ContextPack:
        candidates = self._rank_candidates(intent_graph, repo_profile, target_files, repo_path)
        selected = candidates[: self.MAX_FILES]
        trimmed = [self._trim_to_budget(f, target_files) for f in selected]
        total_lines = sum(f.line_count for f in trimmed)

        # 300줄 초과 시 낮은 우선순위 파일부터 제거
        while total_lines > self.MAX_LINES and trimmed:
            removed = trimmed.pop()
            total_lines -= removed.line_count

        return ContextPack(
            files=trimmed,
            total_lines=total_lines,
            hash=_compute_hash(trimmed),
        )

    def _rank_candidates(self, ...) -> list[ContextFile]: ...
    def _trim_to_budget(self, file: ContextFile, targets: list[str]) -> ContextFile: ...
```

### 7.5 Edge-case Fallback & Determinism

- 단일 `P1` 파일이 매우 큰 경우 전체 파일을 넣지 않고 `import block + referenced symbol window + synopsis` 로 축소한다.
- `target_files > 3` 이면 `plan` 단계에서 node split을 먼저 수행한다.
- 어떤 target file도 `P1`/`P2` 컨텍스트를 하나도 얻지 못하면 `insufficient_context=true` 로 표시하고 `manual-review-required` 로 라우팅한다.
- tie-break는 항상 `normalized_path lexical order` 로 끝나야 한다.
- `context_pack_hash` 는 선택된 chunk manifest를 포함해 계산한다.

> 상세 운영 명세: `24-context-pack-determinism.md`

## 8. Repo-aware Normalization

Normalizer 책임:

- file placement correction
- import ordering / alias alignment
- component naming normalization
- token / spacing / color naming alignment
- existing primitives reuse
- helper sprawl 억제

성공 조건:

- convention diff 감소
- lint/type/build green에 더해 reviewer가 봐도 repo-native code처럼 보여야 함

## 9. Sandboxed Runtime Validation Pipeline

Runtime validation은 최소 다음을 포함한다.

1. build
2. typecheck
3. lint
4. targeted tests (존재 시)
5. app boot smoke
6. browser console error capture
7. uncaught runtime exception capture
8. failed network request capture (가능 시)

### Sandbox Policy

- execution root: ephemeral git worktree 또는 container
- network: default deny
- allowed commands: build, typecheck, lint, test, app boot, Playwright
- writable paths: sandbox workspace + artifact dir
- forbidden reads: host secrets, unrelated repo paths
- env redaction: keys/tokens masked in logs

## 10. Visual Regression 설계

### Input
- target image/reference screenshot
- generated app screenshot
- viewport profile
- threshold profile

### Output
- global diff score
- mismatch regions
- reference/current/diff images
- pass/fail decision

### 초기 운영 임계치(assumption, calibration required)

- SSIM `>= 0.92`
- changed pixel ratio `<= 5%`
- critical region overlap `>= 0.90`
- missing critical region count `= 0`

Critical region: CTA, navigation, primary form, hero content.

threshold profile은 `assumption -> provisional -> calibrated -> stale` 상태를 가지며,
comparative release에서 신뢰되는 값은 `calibrated` 뿐이다.

> 상세 운영 명세: `26-benchmark-calibration-ops.md`

## 11. Auto-fix Loop 설계

### Retry 정책

- 기본 최대 시도: 3
- 각 시도는 다음을 기록
  - failure summary
  - fix hypothesis
  - changed files
  - validation delta

### Failure-class 전략

| 실패 유형 | fix 전략 |
| --- | --- |
| build/type/import | import, symbol, type, module resolution 수정 |
| lint/style | normalizer 우선, generator 재호출 최소화 |
| console/runtime | state init, lifecycle, null guard, effect deps 수정 |
| visual mismatch | layout, spacing, component hierarchy, token use 수정 |

auto-fix는 open-ended regeneration이 아니라 **rule-driven repair** 이다.

- 한 시도에는 `primary rule 1개 + optional normalize follow-up 1개` 만 허용
- `package/config/schema/dependency` 변경 필요 시 즉시 `manual-review-required`
- 변경 파일 `> 3` 또는 변경 라인 `> 120` 예상 시 즉시 중단
- 우선순위는 `build/import -> type -> lint -> runtime -> visual`

> 상세 규칙: `23-auto-fix-rulebook.md`

### Non-improving Loop Detection

- 동일 failure class 집합이 2회 연속 반복
- global diff score 개선폭 `< 2%`
- blocker count 감소 없음
- changed file fingerprint가 실질적으로 동일

## 12. Evidence Pack

각 run은 다음 artifact를 남긴다.

- input payload
- repo profile
- intent graph
- generation plan
- generated diff
- normalization report
- runtime validation report
- console/network logs
- visual regression report
- fix attempt history
- scorecard
- release decision

## 13. P0 최소 동작 프로토타입

P0 범위:

- React/Vite/TypeScript repo only
- single screenshot + single prompt
- one page/component generation
- Chromium only
- build + typecheck + lint + screenshot diff
- auto-fix 최대 2회

P0 green 전에는 broader feature expansion 금지.

## 14. Auto-fix Rollback & Checkpoint 설계

evidence pack은 이력 조회 도구이지 복구 도구가 아니다. auto-fix 시도 중 파일 상태를 안전하게 되돌리려면 별도 메커니즘이 필요하다.

### 14.1 Checkpoint 정책

- auto-fix 시도 시작 직전마다 `git checkpoint` 를 생성한다.
- checkpoint ref는 `ddk/fix/{case_id}/attempt-{n}` 형태로 저장한다.
- `FixAttempt` artifact에 checkpoint ref를 포함한다.

### 14.2 Rollback 전략

| 상황 | Rollback 방법 |
| --- | --- |
| single attempt 실패 | checkpoint ref로 `git restore` 또는 stash pop |
| retry budget exhausted | 마지막 successful checkpoint (또는 pre-fix state)로 revert |
| manual-review-required | 사용자에게 checkpoint ref 제공, `ddk rollback` 명령 노출 |

### 14.3 `ddk rollback` CLI

```
ddk rollback --case <case_id>          # 마지막 successful checkpoint로 복원
ddk rollback --case <case_id> --to 0   # pre-fix state로 완전 복원
```

### 14.4 Rollback 완전성 요건

- rollback은 generated files, normalized files, fixture patches 모두를 되돌려야 한다.
- rollback 이후 repo가 `git status --short = clean` 이어야 한다.

---

## 15. Reproducibility Policy

LangGraph state를 저장한다고 해서 LLM 결과가 재현되는 것은 아니다. 재현성은 별도로 설계해야 한다.

### 15.1 LLM Call Metadata Artifact

각 LLM 호출마다 아래를 `LLMCallRecord` 로 저장한다.

| 필드 | 설명 |
| --- | --- |
| `call_id` | UUID |
| `stage` | graph node 이름 |
| `model` | 사용 모델 ID |
| `provider` | LLM provider |
| `model_version` | 모델 버전 |
| `temperature` | 사용 temperature |
| `seed` | seed (지원 시) |
| `context_pack_hash` | context pack 내용의 sha256 |
| `input_token_count` | 실제 입력 토큰 수 |
| `output_token_count` | 실제 출력 토큰 수 |
| `latency_ms` | 응답 지연 ms |
| `timestamp` | ISO 8601 |

### 15.2 Replay 지원

- 동일 case의 context pack은 `context_pack_hash` 로 재구성 가능해야 한다.
- model/provider가 변경된 경우, `LLMCallRecord` 비교를 통해 delta를 식별 가능해야 한다.

### 15.3 Reproducibility Policy 한계

seed/temperature가 같아도 provider 업데이트로 완전 재현은 보장되지 않는다. 따라서 목표는 **exact replay** 가 아니라 **context 동일성 + call metadata 추적** 이다.

---

## 16. Preflight Doctor & Guided Setup

setup 실패가 run 중간에 터지면 복구 비용이 크다. preflight doctor는 실행 전 모든 전제 조건을 검사하고, 실패 항목마다 remediation hint를 제공한다.

### 16.1 Preflight 검사 항목

| 항목 | 검사 방법 | 실패 시 hint |
| --- | --- | --- |
| Python 3.12+ | `python --version` | `uv python install 3.12` |
| `uv` 설치 | `uv --version` | `curl -LsSf https://astral.sh/uv/install.sh | sh` |
| LLM API key | env var / config 존재 + format | `export DDK_LLM_API_KEY=...` |
| Playwright 설치 | `playwright --version` | `uv run playwright install chromium` |
| Build tool (npm/pnpm/yarn) | `node --version` | `nvm install 20` |
| Repo path validity | path exists + git repo | `git init` 또는 경로 수정 |
| Sandbox tool | container or git worktree check | 안내 메시지 |
| Reference image path | file exists + readable | 경로 확인 |
| Write permissions | workspace dir writable | 권한 확인 |

### 16.2 Preflight 출력 형식

```
ddk preflight

✓ Python 3.12.3
✓ uv 0.4.1
✓ LLM API key (DDK_LLM_API_KEY)
✗ Playwright not found
  → Fix: uv run playwright install chromium
✗ Node.js not found (required for build tool)
  → Fix: nvm install 20 && nvm use 20

2 checks failed. Fix above issues and re-run 'ddk preflight'.
```

### 16.3 Preflight Enforcement

- `ddk run` 또는 `ddk ingest` 는 preflight green 없이 시작하지 않는다.
- `--skip-preflight` flag는 CI 환경에서 명시적으로만 허용한다.

---

## 17. Cost Estimation & Model Routing Policy

### 17.1 케이스당 비용 구조

| 단계 | 모델 tier 권장 | 비용 특성 |
| --- | --- | --- |
| `intent_extract` | reasoning-capable | 1회, medium |
| `generate` | code-capable | 1~2회, high |
| `normalize` | fast | 1회, low |
| `auto_fix` × n | code-capable | n회, high |

### 17.2 Model Complexity Routing

- 단순 fix (lint/import/type): fast/cheap model
- visual mismatch fix: reasoning-capable model
- intent extraction: reasoning-capable model
- code generation: code-capable model

### 17.3 Cost Cap Policy

- 케이스당 hard cap: 설정 가능, default = 미설정 (P0 단계)
- cap 초과 시 현재 단계 이후 실행 중단, evidence pack 저장, `cost-limit-exceeded` terminal state로 전환
- 각 run의 estimated cost + actual cost를 evidence pack에 포함

---

## 18. 왜 이 구조가 GSD보다 나아질 수 있는가

GSD의 강점은 범용 orchestration과 process discipline이다. `딸깍`이 그 위를 노리는 지점은 다음이다.

1. visual input를 1급 입력으로 사용
2. runtime truth와 visual truth를 동시에 사용
3. 실패를 bounded self-healing loop로 되돌림
4. context pack + sandbox + threshold calibration으로 실제 운영 공백을 메움
5. **rollback checkpoint로 파일 상태 안전 복구**
6. **reproducibility artifact로 LLM call 추적**
7. **preflight doctor로 setup 실패를 조기 차단**
8. 특정 교차 영역에서만 measured superiority를 주장

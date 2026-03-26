# AI 구현 인계 패키지

## 1. 구현 목표

코딩 AI는 `딸깍`을 generic generator로 구현하면 안 된다. 아래 루프가 제품 코어다.

`ingest -> analyze -> generate -> normalize -> runtime validate -> visual regress -> auto-fix -> certify`

이 루프를 끝까지 관통하지 못하면 구현은 미완성이다.

## 2. 첫 구현 범위(P0 First)

가장 먼저 구현할 범위:

- React/Vite/TypeScript single repo fixture
- one screenshot + one prompt ingestion
- repo scan
- intent graph artifact
- single page/component generation
- normalization
- sandboxed build + typecheck + lint
- Chromium visual diff
- auto-fix 최대 2회
- evidence pack + release decision

이 범위가 green 되기 전 broader features 금지.

## 3. 가장 먼저 작성할 테스트

### Unit first
- `test_retry_budget_controller.py`
- `test_context_pack_builder.py`
- `test_context_budget_policy.py`
- `test_context_pack_edge_cases.py`
- `test_failure_taxonomy_ids.py`
- `test_console_error_classifier.py`
- `test_auto_fix_rule_selection.py`
- `test_auto_fix_rule_guardrails.py`
- `test_visual_diff_scoring.py`
- `test_visual_region_detector.py`
- `test_release_rule_aggregation.py`
- `test_checkpoint_policy.py`
- `test_rollback_rules.py`
- `test_rollback_failure_modes.py`
- `test_llm_call_record_schema.py`
- `test_context_pack_hash.py`
- `test_prompt_version_policy.py`
- `test_benchmark_state_machine.py`
- `test_threshold_profile_policy.py`
- `test_preflight_checks.py`
- `test_remediation_hints.py`

### Integration first
- `test_init_workspace.py`
- `test_repo_scan_fixtures.py`
- `test_runtime_validation_pipeline.py`
- `test_visual_regression_runner.py`
- `test_auto_fix_loop.py`
- `test_sandbox_runner.py`
- `test_git_checkpoint.py`
- `test_rollback_integration.py`
- `test_rollback_recovery_failure_modes.py`
- `test_benchmark_runner_ops.py`
- `test_preflight_doctor_integration.py`

### Contract first
- `test_case_input_schema.py`
- `test_graph_state_schema.py`
- `test_runtime_validation_schema.py`
- `test_visual_report_schema.py`
- `test_scorecard_schema.py`
- `test_release_decision_schema.py`
- `test_llm_call_record_contract.py`

## 4. Mergeable 전에 반드시 존재해야 하는 테스트

- touched requirement의 primary test level suite
- runtime validation touched code의 integration tests
- visual regression touched code의 integration tests
- auto-fix/retry controller touched code의 unit + integration tests
- context pack 변경 시 unit + contract tests
- sandbox policy 변경 시 unit + integration + denial test
- schema 변경 시 contract tests
- bug fix 시 lowest reliable layer regression test
- auto-fix touched code 시 checkpoint creation/revert integration test
- LLM-calling code 변경 시 LLMCallRecord contract test
- preflight check 변경 시 unit + integration test

## 5. Schema 변경 전 필수 테스트

- artifact schema contract tests
- backward compatibility tests
- schema version migration tests
- release decision compatibility tests
- benchmark scorecard schema tests

## 6. 어떤 사용자 여정이 E2E가 필요한가

반드시 E2E가 필요한 것만 유지한다.

1. ingest -> generate -> build pass
2. runtime failure -> auto-fix -> pass
3. visual mismatch -> blocked
4. retry budget exhausted -> manual review
5. benchmark + certify
6. sandbox violation denied

## 7. Unit test 수준에 남겨야 할 로직

아래는 E2E로 올리지 말고 unit에 남겨야 한다.

- failure taxonomy mapping
- auto-fix rule selection and guardrails
- retry budget rules
- non-improving loop detection
- context compaction rules
- context edge-case trimming rules
- score aggregation
- release blocker aggregation
- threshold pass/fail rules
- threshold profile state policy
- repo normalization rules
- artifact reducers

## 8. 높은 위험의 Integration Seams

1. repo scan -> generation plan
2. generation -> normalization
3. normalization -> runtime validation
4. runtime validation -> failure classifier
5. failure classifier -> auto-fix planner
6. auto-fix -> context compaction on retry
7. Playwright capture -> visual diff engine
8. sandbox runner -> command allowlist enforcement
9. scorecard service -> release decision

## 9. 구현 순서 권장안

1. workspace + schema + artifacts
2. failure taxonomy + retry controller
3. context pack builder + graph state
4. sandbox runner
5. runtime validation pipeline
6. visual regression runner
7. minimal generator adapter
8. auto-fix loop
9. benchmark + release decision

## 10. 금지 사항

- sandbox 밖에서 build/app boot/Playwright 실행 금지
- baseline artifact 없이 superiority claim 금지
- UI regression을 runtime-only green으로 통과시키기 금지
- infinite auto-fix loop 금지
- E2E로 deterministic rule logic를 대체하기 금지
- unresolved critical mismatch를 warning으로 강등하기 금지

## 11. 구현 중 의사결정 원칙

- breadth보다 P0 completion 우선
- fake provider보다 artifact fidelity 우선
- LLM quality보다 validation/correction loop 우선
- human override보다 deterministic gate 우선
- large prompt보다 compact structured context 우선

## 12. 추천 프롬프트

### Unit-test generation prompt
> `RetryBudgetController`, `FailureTaxonomy`, `ContextPackBuilder`, `ReleaseDecisionReducer` 에 대한 deterministic unit tests를 작성하라. 경계값, 반복 실패, non-improving detection, budget 초과, schema version drift를 포함하라.

### Integration-test generation prompt
> React/Vite fixture repo 기준으로 `repo scan -> generate -> normalize -> sandboxed runtime validation` 경로의 integration tests를 작성하라. build/type/lint/runtime failures를 모두 구조화된 report로 남기는지 검증하라.

### Contract-test generation prompt
> Pydantic artifacts(`CaseInput`, `RepoProfile`, `IntentGraph`, `RuntimeValidationReport`, `VisualRegressionReport`, `Scorecard`, `ReleaseDecision`)의 schema compatibility tests를 작성하라. backward compatibility와 required field drift를 검증하라.

### E2E scenario generation prompt
> `ingest -> generate -> validate -> visual-check -> auto-fix -> certify` 루프의 release-critical 시나리오 6개만 E2E로 작성하라. browser retry는 1회만 허용하고 실패 시 screenshot, trace, logs를 저장하라.

### Regression-test generation prompt
> 재현 가능한 실패를 먼저 fixture로 만들고, lowest reliable layer에 regression test를 추가한 뒤 fix를 구현하라. user-visible blocker인 경우에만 integration 또는 E2E를 확장하라.

### Context-pack test prompt
> node별 context pack builder를 검증하는 tests를 작성하라. token budget, optional context trimming, retry compaction, repeated error hashing, manual-review fallback을 포함하라.

### Sandbox-policy test prompt
> sandbox runner에 대해 허용 명령, writable path, network deny, forbidden path access, secret redaction을 검증하는 tests를 작성하라. 우회 시도는 blocked artifact를 남겨야 한다.

### Rollback & checkpoint test prompt
> `CheckpointManager`, `RollbackController` 에 대한 tests를 작성하라. fix attempt 시작 전 checkpoint가 생성되는지, exhausted retry 후 revert가 성공하는지, `ddk rollback --to 0` 이 pre-fix 상태를 완전히 복원하는지를 fixture temp repo에서 검증하라.

### Reproducibility test prompt
> `LLMCallRecorder` 에 대한 tests를 작성하라. model/provider/temperature/seed/schema_version이 모든 LLM 호출마다 저장되는지, context_pack_hash가 동일 context에서 동일 hash를 생성하는지, provider 변경 시 LLMCallRecord delta가 식별 가능한지를 검증하라.

### Preflight doctor test prompt
> `PreflightDoctor` 에 대한 tests를 작성하라. Python 버전, uv, API key, Playwright, Node.js, repo path validity, write permission을 각각 검사하고, 실패 항목마다 remediation hint를 포함한 structured error를 출력하는지 검증하라. preflight green 없이 `ddk run` 이 시작되지 않는지도 확인하라.

### Auto-fix rulebook test prompt
> `23-auto-fix-rulebook.md` 기준으로 failure taxonomy를 deterministic repair rule에 매핑하는 tests를 작성하라. 동일 failure family에서 tie-break가 deterministic인지, 금지된 patch scope(config/dependency/schema 변경)가 manual review로 승격되는지 검증하라.

### Benchmark / calibration ops test prompt
> `26-benchmark-calibration-ops.md` 기준으로 baseline state(`placeholder`, `provisional`, `calibrated`, `stale`)와 threshold profile state 전이를 검증하는 tests를 작성하라. placeholder artifact가 comparative release gate를 통과하지 못하는지, prompt major/provider change가 stale 전이를 일으키는지 확인하라.

## 13. 구현 완료 기준

아래를 만족해야 mergeable이 아니라 **제품 코어 구현 완료**로 간주한다.

- P0 prototype green
- runtime validation green
- visual regression green
- auto-fix bounded retry green
- rollback checkpoint green (fix attempt revert 성공)
- reproducibility artifacts present (LLMCallRecord in evidence pack)
- preflight doctor green (모든 필수 의존성 확인됨)
- sandbox violation denied
- evidence pack complete
- release decision emitted
- baseline artifact 없이 superiority claim 안 함
- comparative release라면 threshold profile `calibrated`
- comparative release라면 baseline artifact state `!= placeholder/stale`

## 14. 최종 품질 바

`딸깍`은 "코드를 한 번 생성했다" 로 끝나면 실패다.

정답은 다음과 같다.

- 생성했다
- repo에 맞게 정리했다
- sandbox에서 실행 검증했다
- 시각적으로 검증했다
- 실패를 제한적으로 고쳤다
- 왜 통과했고 왜 막혔는지 artifact로 설명했다

여기까지 해야 `딸깍`이다.

---

## 15. Multi-tool Adapter 구현 지침

### 구현 우선순위

`ddk mcp` 서버를 **P0 다음 첫 번째로** 구현해야 한다.  
MCP가 없으면 Claude Code, Copilot, OpenCode 연동이 불가능하다.

### 명령 체계 SSoT

- authoritative source: `14-cli-spec.md`
- canonical CLI surface: 16개 (`preflight`, `ingest`, `analyze`, `plan`, `generate`, `validate`, `visual-check`, `fix`, `certify`, `rollback`, `run`, `design`, `install`, `mcp`, `status`, `init`)
- adapter는 한국어/도구별 alias를 제공할 수 있지만, 최종적으로는 canonical CLI 또는 `ddk mcp` tool contract로 매핑되어야 한다.

### 구현 순서

10. MCP Server (`ddk/mcp_server.py` — `FastMCP` 기반)
    - tool 목록: `ddk_ingest`, `ddk_analyze`, `ddk_plan`, `ddk_generate`, `ddk_validate`, `ddk_visual_check`, `ddk_fix`, `ddk_certify`, `ddk_run`, `ddk_rollback`, `ddk_status`
    - transport: stdio (기본). HTTP는 vNext로 유보
11. Claude Code Adapter (`ddk install --adapter claude`)
    - `.claude/commands/ddk/` 아래 wrapper 8개 생성 (`preflight`, `init`, `design`, `run`, `validate`, `visual-check`, `status`, `rollback`)
    - `.mcp.json` ddalggak MCP 등록
12. Copilot Adapter (`ddk install --adapter copilot`)
    - `.github/skills/ddalggak-*/skill.md` 8개
    - `.github/agents/ddalggak-*.md` 5개
13. Gemini CLI Adapter (`ddk install --adapter gemini`)
    - `.gemini/extensions/ddalggak/extension.json`
    - tool 목록은 canonical CLI wrapper 기준 8개 이상
14. OpenCode + Codex Adapter
    - `opencode.json` MCP 등록
    - `.codex/instructions.md`

### MCP Server 구현 추천 프롬프트

> `FastMCP` 라이브러리를 사용해 `ddk mcp` 서버를 구현하라. `ddk_ingest`, `ddk_analyze`, `ddk_plan`, `ddk_generate`, `ddk_validate`, `ddk_visual_check`, `ddk_fix`, `ddk_certify`, `ddk_run`, `ddk_rollback`, `ddk_status` 11개 tool을 정의하라. 각 tool은 `14-cli-spec.md` 의 canonical CLI contract를 호출하거나 동일한 service layer를 직접 호출해야 한다. stdio transport를 기본으로 하고, 모든 tool은 JSON artifact path 또는 structured JSON을 반환해야 한다.

### Claude Adapter 구현 추천 프롬프트

> `ddk install --adapter claude` 커맨드 구현. `templates/claude-commands/` 아래 `preflight`, `init`, `design`, `run`, `validate`, `visual-check`, `status`, `rollback` 8개 `.md` 템플릿 파일을 읽어서 `.claude/commands/ddk/` 에 생성하고, `.mcp.json` 에 ddalggak MCP server를 등록한다. wrapper는 canonical CLI만 호출해야 하며 idempotent해야 한다.

### Gemini Extension 구현 추천 프롬프트

> `ddk install --adapter gemini` 커맨드 구현. `extension.json` 을 `.gemini/extensions/ddalggak/` 에 생성한다. Gemini CLI extension spec에 맞는 JSON Schema로 `ddk_preflight`, `ddk_init`, `ddk_design`, `ddk_run`, `ddk_validate`, `ddk_visual_check`, `ddk_status`, `ddk_rollback` 8개 wrapper tool을 정의하고, 각 tool은 canonical CLI subprocess를 실행한다.

### Mergeable 전 Multi-tool 필수 조건

- `test_mcp_server_tools.py` contract test green
- `test_install_adapter_claude.py` integration test green
- `test_install_adapter_copilot.py` integration test green
- `test_install_adapter_gemini.py` integration test green
- `test_extension_json_schema.py` contract test green
- `test_claude_command_files.py` contract test green
- `test_github_skill_files.py` contract test green

---

## 16. 설계 문서 구현 매핑 (Round 4 완성)

코딩 AI는 구현 전 반드시 아래 문서를 참조한다.

| 구현 대상 | 참조 문서 | 핵심 내용 |
|---------|---------|---------|
| Pydantic 모델 전체 | `12-data-models.md` | 타입, 필드, validator 완전 정의 |
| LLM 어댑터 | `11-llm-interface.md` | AnthropicAdapter, LLMCallRecord, CostTracker |
| 프롬프트 템플릿 | `16-prompt-design.md` | 6개 핵심 프롬프트, token budget, tool use schema |
| Sandbox 구현 | `15-sandbox-design.md` | WorktreeSandbox, CommandAllowlist, RollbackController |
| CLI 명령 | `14-cli-spec.md` | 서브커맨드 16개 전체 인자/옵션/종료 코드 |
| 프로젝트 구조 | `13-project-structure.md` | 디렉토리, pyproject.toml, import 경로 |
| Benchmark 실행 | `17-benchmark-baseline.md` | Scorecard 계산식, BM-001~005 케이스, harness |
| Reproducibility | `18-reproducibility.md` | seed 정책, context_pack_hash, replay |
| 멀티툴 어댑터 | `10-multi-tool-adapter.md` | 5개 도구 설치 경로, MCP server |
| LangGraph builder | `19-langgraph-builder.md` | StateGraph 코드, node signature, edge routing |
| Playwright adapter | `20-playwright-adapter.md` | app boot detection, screenshot capture, runtime aggregation |
| CI workflow | `21-ci-workflow.md` | GitHub Actions gate, pre-commit, pytest 설정 |
| Fixture repo | `22-fixture-spec.md` | P0 React/Vite/TS fixture 실제 파일 내용 |
| Auto-fix rule engine | `23-auto-fix-rulebook.md` | failure taxonomy -> deterministic repair rules |
| Context pack determinism | `24-context-pack-determinism.md` | edge-case trimming, manifest/hash, insufficient-context routing |
| Rollback recovery SOP | `25-rollback-recovery-sop.md` | rollback failure matrix, verify-only, operator steps |
| Benchmark/calibration ops | `26-benchmark-calibration-ops.md` | baseline states, threshold states, superiority claim gate |

### 구현 시작 전 체크리스트

```
[ ] 12-data-models.md 완독 → 첫 코드 라인 전에 models/ 파일 생성
[ ] 13-project-structure.md로 빈 디렉토리 구조 생성
[ ] pyproject.toml 13-project-structure.md 기준으로 작성
[ ] 16-prompt-design.md에서 PROMPT_VERSIONS 초기화
[ ] 11-llm-interface.md에서 FakeLLMAdapter 먼저 구현 (테스트용)
[ ] 15-sandbox-design.md에서 WorktreeSandbox 구현 (격리 실행 필수)
```

### 최소 동작 확인 시퀀스 (P0 smoke test)

```bash
# 1. 환경 확인
ddk preflight

# 2. 픽스처로 케이스 생성
ddk ingest \
  --image fixtures/images/sample-login.png \
  --prompt "로그인 폼 컴포넌트 생성" \
  --repo fixtures/repos/react-vite-ts/ \
  --case-id BM-001

# 3. 파이프라인 실행 (fake LLM으로 E2E smoke)
DDK_LLM_PROVIDER=fake ddk run \
  --image fixtures/images/sample-login.png \
  --prompt "로그인 폼" \
  --repo fixtures/repos/react-vite-ts/ \
  --no-visual

# 4. 상태 확인
ddk status --case-id BM-001 --json
```

## Design Studio 구현 가이드 (DDK-REQ-022 ~ 024)

### 구현 순서

1. `InterviewTurn`, `DesignRequirement` Pydantic 모델 구현 (12-data-models.md §13~14)
2. `DesignDocument`, `StandardsComplianceResult`, `QualityGateScore`, `DesignPackageManifest` 모델 구현 (12-data-models.md §15~18)
3. `RequirementsElicitor` 프롬프트 구현 (16-prompt-design.md §7)
4. `DesignDocSynthesizer` 프롬프트 구현 (16-prompt-design.md §8)
5. `DesignQualityGate` 프롬프트 구현 (16-prompt-design.md §9)
6. Design Studio LangGraph 노드 구현 (19-langgraph-builder.md §7)
7. CLI `ddk design` 커맨드 추가 (14-cli-spec.md 확장)
8. E2E 테스트 추가 (22-fixture-spec.md 확장)

### 테스트 우선순위

| 순위 | 테스트 | 이유 |
| --- | --- | --- |
| 1 | `test_design_requirement_schema.py` | 핵심 데이터 모델 안정성 |
| 2 | `test_interview_turn_parser.py` | 인터뷰 턴 파싱 정확도 |
| 3 | `test_requirement_extractor.py` | 요구사항 추출 규칙 |
| 4 | `test_quality_axis_scoring.py` | 6축 점수 산출 정확도 |
| 5 | `test_hard_block_detector.py` | hard block 감지 정확도 |
| 6 | `test_doc_type_structure.py` | 문서 유형별 표준 구조 |
| 7 | `test_design_doc_synthesis_pipeline.py` | 문서 생성 파이프라인 |
| 8 | `test_quality_gate_pipeline.py` | 품질 게이트 파이프라인 |

### 위험 지점

1. **인터뷰 무한 루프** — `InterviewBudgetController`의 20턴 제한과 saturation 감지가 핵심. 테스트에서 20턴 이상, saturation 조건을 반드시 커버할 것.
2. **10개 문서 부분 생성 실패** — 5번째 문서에서 LLM 실패 시 앞 4개만 저장되는 상황. `DesignPackageManifest`에 partial 상태 필드로 대응.
3. **표준 구조 드리프트** — IEEE 830 등의 표준 구조가 프롬프트에 하드코딩됨. 표준 변경 시 프롬프트 업데이트 필요.
4. **품질 게이트 오탐/미탐** — 6축 점수가 LLM 기반이므로 결정론적이지 않음. fixture 기반 golden test로 보완.

### 참조 문서

| 구현 영역 | 참조 문서 |
| --- | --- |
| Pydantic 모델 | 12-data-models.md §13~18 |
| LLM 프롬프트 | 16-prompt-design.md §7~9 |
| LangGraph 노드 | 19-langgraph-builder.md §7 |
| 표준 매핑 | (Phase 6 구현 후 작성 예정) |
| 품질 기준 | 16-prompt-design.md §10 (품질 게이트 체크리스트) |
| 테스트 매트릭스 | 06-tech-spec.md §14 |

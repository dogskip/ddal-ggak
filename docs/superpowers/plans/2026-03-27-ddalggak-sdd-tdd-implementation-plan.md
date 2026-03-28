# Ddalggak SDD/TDD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 설계 문서를 기준으로 `P0 vertical slice`를 먼저 구현하고, 이후 Design Studio, multi-tool adapter, benchmark/release layer를 확장한다.

**Architecture:** 구현 순서는 PRD의 breadth가 아니라 `실행 가능한 closed-loop kernel` 우선이다. 즉 `workspace -> graph state -> sandbox -> intake -> repo scan -> generate -> validate -> visual-check -> auto-fix -> certify`를 먼저 green으로 만들고, 그 다음 Design Studio와 multi-tool shipping을 붙인다.

**Tech Stack:** Python 3.12+, uv, Typer, Pydantic v2, LangGraph, pytest, Pyright, Ruff, Playwright Python

---

## SDD Rules

- 요구사항 SSoT: [02-prd.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/02-prd.md)
- 구현 순서 SSoT: [06-tech-spec.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/06-tech-spec.md)
- 검증 SSoT: [07-verification-release.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/07-verification-release.md)
- 모델 계약 SSoT: [12-data-models.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/12-data-models.md)
- CLI 계약 SSoT: [14-cli-spec.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/14-cli-spec.md)
- 그래프 계약 SSoT: [19-langgraph-builder.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/19-langgraph-builder.md)
- CI 계약 SSoT: [21-ci-workflow.md](/Users/bjchoi/SynologyDrive/projects/test/ddalggak/docs/design/21-ci-workflow.md)

## TDD Rules

- production code 작성 전 failing test 먼저 작성
- pure logic는 unit test 우선
- schema/JSON/output shape는 contract test 우선
- adapter/sandbox/git/fs는 integration test 우선
- P0 green 전 E2E 확대 금지

---

### Task 1: Project Skeleton And Toolchain

**Files:**
- Create: `pyproject.toml`
- Create: `src/ddk/__init__.py`
- Create: `src/ddk/cli.py`
- Create: `src/ddk/version.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_cli_smoke.py`
- Create: `tests/contract/test_toolchain_contract.py`

- [ ] **Step 1: Write the failing contract tests**
  - CLI entrypoint exists
  - package metadata exists
  - `ddk --version` and `ddk --help` contract is defined
- [ ] **Step 2: Run `uv run pytest tests/unit/test_cli_smoke.py tests/contract/test_toolchain_contract.py -v`**
  - Expected: import/entrypoint failure
- [ ] **Step 3: Implement minimal package skeleton**
  - Typer app only
  - version string only
- [ ] **Step 4: Re-run tests until green**
- [ ] **Step 5: Run `uv run ruff check src tests && uv run pyright src`**
- [ ] **Step 6: Commit**

### Task 2: Contract-First Models And Config

**Files:**
- Create: `src/ddk/models/_base.py`
- Create: `src/ddk/models/input.py`
- Create: `src/ddk/models/repo.py`
- Create: `src/ddk/models/intent.py`
- Create: `src/ddk/models/generation.py`
- Create: `src/ddk/models/release.py`
- Create: `src/ddk/models/llm.py`
- Create: `src/ddk/config.py`
- Test: `tests/contract/test_case_input_schema.py`
- Test: `tests/contract/test_graph_state_schema.py`
- Test: `tests/contract/test_release_decision_schema.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing schema tests from `12-data-models.md`**
- [ ] **Step 2: Run contract tests and confirm field/validator failures**
- [ ] **Step 3: Implement only the P0 models and `DdalggakConfig`**
- [ ] **Step 4: Re-run contract + config tests**
- [ ] **Step 5: Refactor imports so models stay acyclic**
- [ ] **Step 6: Commit**

### Task 3: Workspace, Artifact IO, And Graph State

**Files:**
- Create: `src/ddk/workspace/manager.py`
- Create: `src/ddk/workspace/artifacts.py`
- Create: `src/ddk/graph/state.py`
- Create: `src/ddk/graph/builder.py`
- Test: `tests/integration/test_init_workspace.py`
- Test: `tests/unit/test_graph_state_defaults.py`
- Test: `tests/contract/test_workspace_artifact_layout.py`

- [ ] **Step 1: Write failing tests for `.ddk/` layout, case ID generation, artifact save/load**
- [ ] **Step 2: Run tests and verify missing workspace manager failures**
- [ ] **Step 3: Implement idempotent workspace bootstrap**
- [ ] **Step 4: Implement minimal `GraphState` and empty LangGraph builder**
- [ ] **Step 5: Re-run tests**
- [ ] **Step 6: Commit**

### Task 4: Sandbox, Preflight, Checkpoint, Rollback Kernel

**Files:**
- Create: `src/ddk/adapters/sandbox/base.py`
- Create: `src/ddk/adapters/sandbox/policy.py`
- Create: `src/ddk/adapters/sandbox/worktree.py`
- Create: `src/ddk/preflight/doctor.py`
- Create: `src/ddk/workspace/checkpoint.py`
- Create: `src/ddk/workspace/rollback.py`
- Test: `tests/unit/test_sandbox_policy.py`
- Test: `tests/unit/test_preflight_checks.py`
- Test: `tests/unit/test_checkpoint_policy.py`
- Test: `tests/unit/test_rollback_rules.py`
- Test: `tests/integration/test_sandbox_runner.py`
- Test: `tests/integration/test_git_checkpoint.py`
- Test: `tests/integration/test_rollback_integration.py`

- [ ] **Step 1: Write failing policy tests for command allowlist, writable path restriction, env whitelist**
- [ ] **Step 2: Write failing integration tests on temp git repos**
- [ ] **Step 3: Implement policy objects first**
- [ ] **Step 4: Implement worktree sandbox + checkpoint/rollback**
- [ ] **Step 5: Implement `ddk preflight` kernel with remediation hints**
- [ ] **Step 6: Re-run unit + integration tests**
- [ ] **Step 7: Commit**

### Task 5: Intake, Repo Scan, Design Token Inference

**Files:**
- Create: `src/ddk/services/intake_service.py`
- Create: `src/ddk/services/repo_scanner.py`
- Create: `src/ddk/services/design_system_inferencer.py`
- Create: `src/ddk/graph/nodes/ingest.py`
- Create: `src/ddk/graph/nodes/repo_scan.py`
- Test: `tests/contract/test_intake_input_contract.py`
- Test: `tests/unit/test_repo_scanner.py`
- Test: `tests/integration/test_repo_scan_fixtures.py`

- [ ] **Step 1: Write failing contract tests for image/prompt/repo intake**
- [ ] **Step 2: Write failing repo fixture tests against `fixtures/repos/react-vite-ts/`**
- [ ] **Step 3: Implement intake validation**
- [ ] **Step 4: Implement deterministic repo scanner and token inference**
- [ ] **Step 5: Wire ingest/repo_scan nodes**
- [ ] **Step 6: Re-run tests**
- [ ] **Step 7: Commit**

### Task 6: Intent Extraction And Generation Planning

**Files:**
- Create: `src/ddk/adapters/llm/base.py`
- Create: `src/ddk/adapters/llm/fake.py`
- Create: `src/ddk/adapters/llm/recorder.py`
- Create: `src/ddk/services/intent_extractor.py`
- Create: `src/ddk/services/generation_planner.py`
- Create: `src/ddk/services/context_pack_builder.py`
- Create: `src/ddk/graph/nodes/intent_extract.py`
- Create: `src/ddk/graph/nodes/plan.py`
- Test: `tests/unit/test_context_budget_policy.py`
- Test: `tests/unit/test_context_pack_builder.py`
- Test: `tests/unit/test_llm_call_record_schema.py`
- Test: `tests/unit/test_model_router.py`
- Test: `tests/contract/test_intent_graph_schema.py`
- Test: `tests/integration/test_runtime_validation_pipeline.py`

- [ ] **Step 1: Write failing tests using fake LLM outputs**
- [ ] **Step 2: Verify RED on context budget, intent graph, call record schema**
- [ ] **Step 3: Implement fake adapter + recorder**
- [ ] **Step 4: Implement intent extractor and generation planner with deterministic fixture mode**
- [ ] **Step 5: Wire context pack builder and plan node**
- [ ] **Step 6: Re-run tests**
- [ ] **Step 7: Commit**

### Task 7: Code Generation And Normalization

**Files:**
- Create: `src/ddk/services/code_generator.py`
- Create: `src/ddk/services/normalizer.py`
- Create: `src/ddk/graph/nodes/generate.py`
- Create: `src/ddk/graph/nodes/normalize.py`
- Test: `tests/contract/test_generated_artifact_set_schema.py`
- Test: `tests/unit/test_normalization_rules.py`
- Test: `tests/integration/test_generate_normalize_pipeline.py`

- [ ] **Step 1: Write failing tests for generated file set shape and naming/import normalization**
- [ ] **Step 2: Run tests and confirm missing generator failures**
- [ ] **Step 3: Implement minimal generator using fake LLM response fixtures**
- [ ] **Step 4: Implement deterministic normalizer**
- [ ] **Step 5: Wire generate/normalize nodes**
- [ ] **Step 6: Re-run tests**
- [ ] **Step 7: Commit**

### Task 8: Runtime Validation And Visual Regression

**Files:**
- Create: `src/ddk/adapters/build_runner.py`
- Create: `src/ddk/adapters/playwright_browser.py`
- Create: `src/ddk/adapters/console_capture.py`
- Create: `src/ddk/adapters/screenshot_diff.py`
- Create: `src/ddk/services/runtime_validator.py`
- Create: `src/ddk/services/visual_regression.py`
- Create: `src/ddk/graph/nodes/runtime_validate.py`
- Create: `src/ddk/graph/nodes/visual_regress.py`
- Test: `tests/unit/test_visual_diff_scoring.py`
- Test: `tests/unit/test_failure_taxonomy_ids.py`
- Test: `tests/integration/test_visual_regression_runner.py`
- Test: `tests/e2e/test_runtime_validate_e2e.py`
- Test: `tests/e2e/test_visual_gate_e2e.py`

- [ ] **Step 1: Write failing unit tests for failure taxonomy and diff scoring**
- [ ] **Step 2: Write failing integration test with broken fixture repo**
- [ ] **Step 3: Implement runtime aggregator**
- [ ] **Step 4: Implement screenshot capture and diff adapter**
- [ ] **Step 5: Wire runtime/visual nodes**
- [ ] **Step 6: Run unit + integration first**
- [ ] **Step 7: Run E2E only after integration green**
- [ ] **Step 8: Commit**

### Task 9: Auto-fix Loop, Evidence Pack, Release Decision

**Files:**
- Create: `src/ddk/services/failure_classifier.py`
- Create: `src/ddk/services/retry_controller.py`
- Create: `src/ddk/services/evidence_builder.py`
- Create: `src/ddk/services/release_decision.py`
- Create: `src/ddk/graph/nodes/auto_fix.py`
- Create: `src/ddk/graph/nodes/certify.py`
- Create: `src/ddk/graph/edges.py`
- Test: `tests/unit/test_retry_budget_controller.py`
- Test: `tests/unit/test_release_rule_aggregation.py`
- Test: `tests/integration/test_auto_fix_loop.py`
- Test: `tests/e2e/test_fix_loop_e2e.py`
- Test: `tests/e2e/test_certify_release_e2e.py`

- [ ] **Step 1: Write failing tests for retry budget, blocked/manual-review decisions, evidence completeness**
- [ ] **Step 2: Implement failure taxonomy mapping and retry controller**
- [ ] **Step 3: Implement evidence pack builder and release decider**
- [ ] **Step 4: Implement auto-fix node with fake fixer first**
- [ ] **Step 5: Wire edge routing and terminal state mapping**
- [ ] **Step 6: Re-run unit + integration + selected E2E**
- [ ] **Step 7: Commit**

### Task 10: P0 CLI Vertical Slice

**Files:**
- Modify: `src/ddk/cli.py`
- Create: `src/ddk/commands/preflight.py`
- Create: `src/ddk/commands/ingest.py`
- Create: `src/ddk/commands/analyze.py`
- Create: `src/ddk/commands/generate.py`
- Create: `src/ddk/commands/validate.py`
- Create: `src/ddk/commands/visual_check.py`
- Create: `src/ddk/commands/fix.py`
- Create: `src/ddk/commands/certify.py`
- Create: `src/ddk/commands/run.py`
- Test: `tests/integration/test_cli_vertical_slice.py`

- [ ] **Step 1: Write failing CLI integration test for `ddk run` on fixture repo**
- [ ] **Step 2: Implement command modules only for P0 path**
- [ ] **Step 3: Ensure exit codes match `14-cli-spec.md`**
- [ ] **Step 4: Re-run CLI integration test**
- [ ] **Step 5: Commit**

### Task 11: CI, Fixtures, And P0 Gate

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/release.yml`
- Create: `.pre-commit-config.yaml`
- Create: `fixtures/repos/react-vite-ts/*`
- Create: `fixtures/images/*`
- Modify: `pyproject.toml`
- Test: `tests/e2e/test_generate_basic_e2e.py`
- Test: `tests/e2e/test_sandbox_block_e2e.py`

- [ ] **Step 1: Write failing CI-facing tests for markers, config, and fixture availability**
- [ ] **Step 2: Implement pytest/coverage/pre-commit configuration**
- [ ] **Step 3: Add GitHub Actions workflows from the approved spec**
- [ ] **Step 4: Re-run full local suite: `unit -> contract -> integration -> e2e`**
- [ ] **Step 5: Declare `P0 green` only if all release-blocking tests pass**
- [ ] **Step 6: Commit**

### Task 12: Post-P0 Expansion Only After Green

**Files:**
- Create later: `src/ddk/design_studio/*`
- Create later: `src/ddk/adapters/llm/anthropic.py`
- Create later: `src/ddk/adapters/llm/openai.py`
- Create later: `src/ddk/mcp/server.py`
- Create later: `templates/*`
- Create later: `benchmarks/*`
- Test later: `tests/integration/test_mcp_server_*.py`
- Test later: `tests/contract/test_mcp_server_tools.py`

- [ ] **Step 1: Freeze P0 scope and reject GSD++ breadth creep**
- [ ] **Step 2: Implement Design Studio (`DDK-REQ-022~024`)**
- [ ] **Step 3: Implement multi-tool adapters and MCP server (`DDK-REQ-025~029`)**
- [ ] **Step 4: Implement benchmark/calibration/release proof layer (`DDK-REQ-017~018`)**
- [ ] **Step 5: Run comparative benchmark against GSD only after calibrated thresholds exist**

---

## Milestone Exit Criteria

### Milestone A — Kernel Ready
- Task 1~4 green
- lock, sandbox, rollback, preflight가 모두 integration test로 증명됨

### Milestone B — P0 Delivery Ready
- Task 5~10 green
- `ddk run`이 fixture repo에서 build/type/lint/visual까지 통과

### Milestone C — Productization Ready
- Task 11 green
- CI에서 release-blocking suite가 안정적으로 재현

### Milestone D — Expansion Ready
- Task 12 착수 가능
- P0 benchmark와 threshold calibration 계획 승인

---

## Recommended Execution Order

1. Task 1~4
2. Task 5~7
3. Task 8~10
4. Task 11
5. Task 12

## Explicit Non-Goals For First Build

- GSD full parity 구현
- 실 LLM provider 통합
- Docker sandbox 완성
- multi-page/multi-framework 지원
- superiority marketing claim

## Verification Commands

- Unit: `uv run pytest tests/unit/ -v`
- Contract: `uv run pytest tests/contract/ -v`
- Integration: `uv run pytest tests/integration/ -v -x`
- E2E: `uv run pytest tests/e2e/ -v --timeout=300`
- Static: `uv run ruff check src tests && uv run ruff format --check src tests && uv run pyright src`


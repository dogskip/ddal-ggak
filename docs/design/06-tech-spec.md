# 기술 명세(Tech Spec)

## 1. 구현 스택 제안

- Language: Python 3.12+
- Package Manager: `uv`
- CLI: Typer
- Schema / Validation: Pydantic v2
- Orchestration: LangGraph
- Static checks: Ruff + Pyright
- Testing: pytest
- Browser / Visual: Playwright Python
- Sandbox: container 또는 ephemeral worktree

## 2. P0 프로토타입 범위

- React/Vite/TypeScript single repo only
- one screenshot + one prompt
- single page/component generation
- Chromium only
- build + typecheck + lint + screenshot diff
- auto-fix 최대 2회

P0 green 전 broader scope 금지.

## 3. 정적 검증(Static Checks)

| 체크 | 목적 | 실행 시점 | Release Gate |
| --- | --- | --- | --- |
| `ruff format --check` | 포맷 일관성 | local, PR | yes |
| `ruff check` | 위험 패턴 탐지 | local, PR | yes |
| `pyright` | 타입 안정성 | local, PR | yes |
| Pydantic schema validation | artifact drift 방지 | PR, merge | yes |
| LangGraph topology validation | node/edge completeness | PR, merge | yes |

## 4. 구현 Phase 계획

### Phase 0 — Foundation & Prototype Slice

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-001` Workspace Bootstrap | Integration primary, Unit secondary | workspace init, idempotency | empty repo fixture | real fs | PR | Low | Yes | TDD preferred |
| `DDK-REQ-015` LangGraph State & Context Orchestration | Unit primary, Integration secondary, Contract secondary | node transitions, retry branching, context budgets | graph fixtures, context budget fixtures | pure graph unit, real artifact integration | PR | Medium | Yes | TDD required |
| `DDK-REQ-016` Sandboxed Execution Policy | Integration primary, Unit secondary | command allowlist, writable path restriction, blocked execution | sandbox violation fixtures | real sandbox runner on temp repos | PR + Merge | Medium | Yes | TDD required |
| `DDK-REQ-019` Auto-fix Rollback & Checkpoint | Unit primary, Integration secondary | checkpoint creation, revert execution, rollback CLI | broken-state fixtures, exhausted-retry fixtures | real git ops on temp repos | PR + Merge | Medium | Yes | TDD required |
| `DDK-REQ-020` Reproducibility & LLM Call Metadata | Unit primary, Contract secondary | LLMCallRecord schema, context_pack_hash, replay context build | LLM mock call fixtures | fake LLM calls unit, real context packing integration | PR | Low | Yes | TDD required |
| `DDK-REQ-021` Preflight Doctor & Guided Setup | Unit primary, Integration secondary | per-check logic, remediation hint output, enforcement gate | missing-dependency fixtures | real env detection | PR | Low | Yes | TDD required |

### Phase 1 — Intake & Understanding

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-002` Multimodal Intake | Contract primary, Integration secondary | input schema, malformed inputs, normalization | sample images, malformed inputs | fake image metadata, real fs | PR | Low | Yes | TDD required |
| `DDK-REQ-003` Repo Convention Scan | Unit primary, Integration secondary | framework/style/layout detection | React/Vite fixtures | real fixture repos | PR | Medium | Yes | TDD required |
| `DDK-REQ-004` Semantic Intent Model | Unit primary, Contract secondary, Integration secondary | intent graph shape, confidence handling, unresolved items | annotated intent fixtures | fake inference outputs unit, pipeline integration | PR | Medium | Yes | TDD preferred |
| `DDK-REQ-005` Design System Inference | Unit primary, Integration secondary | token/primitives inference | Tailwind/shadcn fixtures | real repo fixtures | PR | Medium | Yes | TDD preferred |

### Phase 2 — Planning, Generation, Normalization

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-006` Generation Plan Graph | Unit primary, Integration secondary | node graph creation, dependencies, hooks | prompt+intent fixtures | pure graph unit | PR | Medium | Yes | TDD required |
| `DDK-REQ-007` Code Generation Engine | Integration primary, Contract secondary | generated file set shape, trace capture | fake LLM outputs, golden file fixtures | fake LLM in PR, dogfood later | PR + Staging | Medium | Yes | TDD optional but tests required before merge |
| `DDK-REQ-008` Post-generation Normalizer | Unit primary, Integration secondary | naming/import/token/file placement normalization | drift fixtures | real repo fixtures | PR | Medium | Yes | TDD required |

### Phase 3 — Validation & Self-healing

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-009` Sandboxed Runtime Validation Pipeline | Integration primary, Unit secondary | build/type/lint/runtime aggregation, failure taxonomy, sandbox enforcement | broken build/type/lint/runtime fixtures | real commands inside sandbox | PR + Merge | High | Yes | TDD preferred |
| `DDK-REQ-010` Console & Runtime Error Capture | Integration primary, Contract secondary | browser console capture, runtime exception parsing | failing runtime fixtures | real Playwright browser | Merge | Medium | Yes | TDD preferred |
| `DDK-REQ-011` Visual Regression Runner | Integration primary, Unit secondary, E2E secondary | screenshot capture, diff score, mismatch localization | reference screenshot fixtures | real browser + fake thresholds | Merge + Staging | High | Yes | TDD preferred |
| `DDK-REQ-012` Bounded Auto-fix Loop | Unit primary, Integration secondary, E2E secondary | retry control, loop compaction, fix lifecycle | failing case fixtures, non-improving loop fixtures | fake fixer unit, real validation integration | Merge + Release | High | Yes | TDD required |
| `DDK-REQ-013` Failure Taxonomy | Unit primary, Contract secondary | failure IDs, stable mapping rules | error fixtures | pure unit | PR | Low | Yes | TDD required |
| `DDK-REQ-014` Evidence Pack Builder | Unit primary, Integration secondary, Contract secondary | artifact packaging, replay completeness | partial-failure fixtures | real artifact integration | PR + Merge | Medium | Yes | TDD required |

### Phase 4 — Benchmark & Release

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-017` Comparative Benchmark & Scorecard | Unit primary, Integration secondary, Contract secondary | score aggregation, baseline comparison, category-bound reporting | score fixtures, baseline artifact fixtures | fake scorer unit, real harness integration | Merge + Release | Medium | Yes | TDD required |
| `DDK-REQ-018` Release Decision / Perfection Gate | Integration primary, Unit secondary, Contract secondary | blocker aggregation, ready/blocked/manual-review decision | critical defect fixtures, exhausted-loop fixtures | real artifact aggregation | Release | Medium | Yes | TDD preferred |

## 5. 요구사항별 검증 경로

| Requirement ID | Primary Test Level | Secondary Test Level | Automation Status | Release-Gating Status | Rationale |
| --- | --- | --- | --- | --- | --- |
| `DDK-REQ-001` | Integration | Unit | Automated | Gating | 파일 구조와 재실행 안정성이 핵심 |
| `DDK-REQ-002` | Contract | Integration | Automated | Gating | input schema 안정성이 우선 |
| `DDK-REQ-003` | Unit | Integration | Automated | Gating | convention classifier는 deterministic 규칙 중심 |
| `DDK-REQ-004` | Unit | Contract, Integration | Automated | Gating | intent graph shape와 unresolved handling 검증 |
| `DDK-REQ-005` | Unit | Integration | Automated | Gating | token inference rules는 하위 레이어 검증 가능 |
| `DDK-REQ-006` | Unit | Integration | Automated | Gating | graph ordering과 hook wiring이 pure logic 중심 |
| `DDK-REQ-007` | Integration | Contract | Automated + Dogfood | Gating | generation은 adapter/LLM 경계가 커서 integration 우선 |
| `DDK-REQ-008` | Unit | Integration | Automated | Gating | normalization rules는 deterministic |
| `DDK-REQ-009` | Integration | Unit | Automated | Gating | runtime 경계와 sandbox enforcement를 다뤄야 함 |
| `DDK-REQ-010` | Integration | Contract | Automated | Gating | browser/runtime capture는 실제 실행 경계 검증 필요 |
| `DDK-REQ-011` | Integration | Unit, E2E | Automated | Gating | screenshot capture + diff는 integration 우선 |
| `DDK-REQ-012` | Unit | Integration, E2E | Automated | Gating | retry control은 deterministic, 효과는 integration/E2E에서 확인 |
| `DDK-REQ-013` | Unit | Contract | Automated | Gating | failure IDs는 stable rule set |
| `DDK-REQ-014` | Unit | Integration, Contract | Automated | Gating | evidence completeness는 reducer + packaging 로직 중심 |
| `DDK-REQ-015` | Unit | Integration, Contract | Automated | Gating | graph state와 context packing policy가 핵심 |
| `DDK-REQ-016` | Integration | Unit | Automated | Gating | execution safety는 실제 sandbox enforcement가 핵심 |
| `DDK-REQ-017` | Unit | Integration, Contract | Automated | Gating | score aggregation과 baseline comparison이 pure logic 중심 |
| `DDK-REQ-018` | Integration | Unit, Contract | Automated | Gating | release는 다중 artifact aggregation이므로 integration 우선 |
| `DDK-REQ-019` | Unit | Integration | Automated | Gating | checkpoint 생성/revert는 git ops이므로 integration 필수 |
| `DDK-REQ-020` | Unit | Contract | Automated | Gating | LLMCallRecord는 deterministic schema + context hash 규칙 중심 |
| `DDK-REQ-021` | Unit | Integration | Automated | Gating | per-check logic은 unit, 실제 env 검사는 integration |
| `DDK-REQ-022` | Unit | Integration | Automated | Gating | 인터뷰 턴 파싱과 요구사항 추출은 deterministic 규칙 중심 |
| `DDK-REQ-023` | Integration | Contract | Automated + Dogfood | Gating | 문서 생성은 LLM 경계를 포함하므로 integration 우선 |
| `DDK-REQ-024` | Unit | Integration, Contract | Automated | Gating | 6축 점수 산출은 규칙 기반, 교차 검증은 integration |

## 6. 기능 / 요구사항 테스트 매트릭스

| Feature / Requirement ID | Unit | Integration | Contract | E2E | Manual | TDD Mode | Release Gate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-001` | `test_workspace_rules.py` | `test_init_workspace.py` | `test_workspace_schema.py` | `test_init_smoke_e2e.py` | - | TDD preferred | PR |
| `DDK-REQ-002` | `test_input_normalizer.py` | `test_multimodal_ingest.py` | `test_case_input_schema.py` | - | - | TDD required | PR |
| `DDK-REQ-003` | `test_repo_scan_classifier.py` | `test_repo_scan_fixtures.py` | `test_repo_profile_schema.py` | - | - | TDD required | PR |
| `DDK-REQ-004` | `test_intent_graph_rules.py` | `test_intent_pipeline.py` | `test_intent_schema.py` | - | sample review | TDD preferred | PR |
| `DDK-REQ-005` | `test_design_token_rules.py` | `test_design_inference.py` | `test_design_profile_schema.py` | - | - | TDD preferred | PR |
| `DDK-REQ-006` | `test_plan_graph_rules.py` | `test_plan_graph_integration.py` | `test_plan_graph_schema.py` | - | - | TDD required | PR |
| `DDK-REQ-007` | `test_generation_trace_rules.py` | `test_code_generation_pipeline.py` | `test_generated_artifact_schema.py` | `test_generate_basic_e2e.py` | dogfood review | TDD optional but tests required before merge | Staging |
| `DDK-REQ-008` | `test_normalizer_rules.py` | `test_normalizer_repo_alignment.py` | `test_normalization_report_schema.py` | - | review diff | TDD required | PR |
| `DDK-REQ-009` | `test_failure_taxonomy.py` | `test_runtime_validation_pipeline.py` | `test_runtime_validation_schema.py` | `test_runtime_validate_e2e.py` | sandbox smoke review | TDD preferred | Merge |
| `DDK-REQ-010` | `test_console_parser_rules.py` | `test_console_runtime_capture.py` | `test_runtime_capture_schema.py` | `test_console_capture_e2e.py` | - | TDD preferred | Merge |
| `DDK-REQ-011` | `test_visual_diff_scoring.py` | `test_visual_regression_runner.py` | `test_visual_report_schema.py` | `test_visual_gate_e2e.py` | reference eyeball check | TDD preferred | Release |
| `DDK-REQ-012` | `test_retry_budget_controller.py`, `test_context_pack_builder.py` | `test_auto_fix_loop.py`, `test_retry_context_compaction.py` | `test_fix_attempt_schema.py` | `test_fix_loop_e2e.py` | - | TDD required | Release |
| `DDK-REQ-013` | `test_failure_taxonomy_ids.py` | `test_failure_taxonomy_integration.py` | `test_failure_taxonomy_schema.py` | - | - | TDD required | PR |
| `DDK-REQ-014` | `test_audit_reducer.py` | `test_evidence_pack.py` | `test_evidence_pack_schema.py` | - | - | TDD required | Merge |
| `DDK-REQ-015` | `test_graph_state_transitions.py`, `test_context_budget_policy.py` | `test_langgraph_pipeline.py` | `test_graph_state_schema.py` | `test_full_graph_smoke_e2e.py` | - | TDD required | PR |
| `DDK-REQ-016` | `test_sandbox_policy.py` | `test_sandbox_runner.py` | `test_sandbox_metadata_schema.py` | `test_sandbox_block_e2e.py` | - | TDD required | Merge |
| `DDK-REQ-017` | `test_scorecard_rules.py` | `test_benchmark_pipeline.py` | `test_scorecard_schema.py` | `test_benchmark_gate_e2e.py` | baseline review | TDD required | Release |
| `DDK-REQ-018` | `test_release_rule_aggregation.py` | `test_release_decision_pipeline.py` | `test_release_decision_schema.py` | `test_certify_release_e2e.py` | release review | TDD preferred | Release |
| `DDK-REQ-019` | `test_checkpoint_policy.py`, `test_rollback_rules.py` | `test_git_checkpoint.py`, `test_rollback_integration.py` | `test_fix_attempt_schema.py` | `test_rollback_e2e.py` | - | TDD required | Merge |
| `DDK-REQ-020` | `test_llm_call_record_schema.py`, `test_context_pack_hash.py` | `test_reproducibility_pipeline.py` | `test_llm_call_record_contract.py` | - | - | TDD required | PR |
| `DDK-REQ-021` | `test_preflight_checks.py`, `test_remediation_hints.py` | `test_preflight_doctor_integration.py` | - | `test_preflight_block_e2e.py` | - | TDD required | PR |
| `DDK-REQ-022` | `test_interview_turn_parser.py`, `test_requirement_extractor.py` | `test_requirements_elicitation_pipeline.py` | `test_design_requirement_schema.py` | - | TDD required | PR |
| `DDK-REQ-023` | `test_doc_type_structure.py` | `test_design_doc_synthesis_pipeline.py` | `test_design_document_schema.py`, `test_compliance_result_schema.py` | `test_design_synthesis_e2e.py` | TDD preferred | Staging |
| `DDK-REQ-024` | `test_quality_axis_scoring.py`, `test_hard_block_detector.py` | `test_quality_gate_pipeline.py` | `test_quality_gate_score_schema.py` | `test_quality_gate_e2e.py` | TDD required | Merge |

## 7. TDD 적용 규칙

### TDD Required
- `DDK-REQ-002`, `003`, `006`, `008`, `012`, `013`, `014`, `015`, `016`, `017`, `019`, `020`, `021`, `022`, `024`

### TDD Preferred
- `DDK-REQ-001`, `004`, `005`, `009`, `010`, `011`, `018`, `023`

### TDD Optional but Tests Required Before Merge
- `DDK-REQ-007`
- 이유: actual generation은 LLM/inference boundary를 포함하므로 fixture-driven contract/integration이 더 현실적이다.

## 8. 통합 테스트 정책

Integration tests must verify:

- ingest -> repo scan -> intent model
- plan -> generate -> normalize
- normalize -> runtime validation
- runtime validation -> visual regression
- failure classification -> auto-fix planner -> retry controller
- context pack builder -> LLM adapter envelope
- sandbox runner -> command enforcement
- benchmark score aggregation
- release decision aggregation

## 9. Contract 테스트 정책

Contract tests must verify:

- Pydantic artifact schemas
- CLI `--json` outputs
- runtime validation report shape
- visual regression report shape
- fix attempt artifact shape
- scorecard artifact shape
- release decision artifact shape
- sandbox metadata shape

## 10. E2E 범위 제한

release-critical E2E는 아래만 유지한다.

1. image+prompt ingestion -> generate -> build pass
2. visual regression gate pass/fail
3. runtime failure -> auto-fix -> pass
4. repeated failure -> retry budget exhausted -> manual review
5. benchmark scorecard and release certification
6. sandbox violation -> blocked

## 11. 비기능 테스트(NFR Test) 설계

| 영역 | 테스트 |
| --- | --- |
| Precision | intent fixtures vs output mapping audit |
| Maintainability | convention drift before/after normalizer |
| Automation | fix-loop success rate + intervention rate |
| Runtime correctness | build/type/lint/runtime/console pass |
| Visual fidelity | screenshot diff within threshold |
| Context efficiency | token budget + compaction audit |
| Execution safety | sandbox enforcement suite |
| Perfection gate | known critical/blocker zero check |

## 12. Mergeable 최소 조건

구현은 아래 없이는 mergeable이 아니다.

- 해당 requirement의 primary test suite 존재
- release-gating requirement의 automated path 존재
- runtime/visual/autofix/context/sandbox touched code에는 regression fixture 추가
- schema 변경 시 contract tests 존재
- bug fix 시 lowest reliable layer regression test 존재

## 13. Multi-tool Adapter Phase (신규)

### Phase 5 — Multi-tool Adapter & MCP Server

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-025` Claude Code Adapter | Contract primary, Integration secondary | `.claude/commands/ddk/*.md` 파일 형식, MCP 연결 | empty repo fixture | real file creation | PR | Low | Yes | TDD required |
| `DDK-REQ-026` Copilot Adapter | Contract primary, Integration secondary | `.github/skills/ddalggak-*` 형식, agent 파일 형식 | empty repo fixture | real file creation | PR | Low | Yes | TDD required |
| `DDK-REQ-027` Gemini CLI Adapter | Contract primary, Integration secondary | `extension.json` 스키마, tool 정의 완전성 | empty repo fixture | real file creation | PR | Low | Yes | TDD required |
| `DDK-REQ-028` OpenCode + Codex Adapter | Integration primary, Contract secondary | `opencode.json` MCP 등록, `.codex/instructions.md` 형식 | empty repo fixture | real file creation | PR | Low | Yes | TDD required |
| `DDK-REQ-029` MCP Server | Contract primary, Integration secondary, E2E secondary | tool 목록 schema, stdio transport, tool call 성공 | MCP client fixture | real MCP server | PR + Merge | Medium | Yes | TDD required |

### 요구사항별 검증 경로 (Multi-tool)

| Requirement ID | Primary Test Level | Secondary Test Level | Automation Status | Release-Gating | Rationale |
| --- | --- | --- | --- | --- | --- |
| `DDK-REQ-025` | Contract | Integration | Automated | Gating | 파일 형식이 Claude SDK 기대치와 일치해야 함 |
| `DDK-REQ-026` | Contract | Integration | Automated | Gating | GSD와 같은 파일 패턴이어야 함 |
| `DDK-REQ-027` | Contract | Integration | Automated | Gating | Gemini extension schema가 spec과 일치해야 함 |
| `DDK-REQ-028` | Integration | Contract | Automated | Gating | MCP 등록 + instructions 파일 생성 |
| `DDK-REQ-029` | Contract | Integration, E2E | Automated | Gating | MCP tool schema + transport 동작이 핵심 |

### 테스트 매트릭스 (Multi-tool)

| Feature / Requirement ID | Unit | Integration | Contract | E2E | TDD Mode | Release Gate |
| --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-025` | `test_claude_command_generator.py` | `test_install_adapter_claude.py` | `test_claude_command_files.py` | - | TDD required | PR |
| `DDK-REQ-026` | `test_copilot_skill_generator.py` | `test_install_adapter_copilot.py` | `test_github_skill_files.py` | - | TDD required | PR |
| `DDK-REQ-027` | `test_gemini_extension_builder.py` | `test_install_adapter_gemini.py` | `test_extension_json_schema.py` | - | TDD required | PR |
| `DDK-REQ-028` | `test_opencode_config_builder.py` | `test_install_adapter_opencode.py`, `test_install_adapter_codex.py` | `test_opencode_config_schema.py` | - | TDD required | PR |
| `DDK-REQ-029` | - | `test_mcp_server_design.py`, `test_mcp_server_execute.py` | `test_mcp_server_tools.py` | `test_mcp_tool_use_e2e.py` | TDD required | Merge |

## 14. Design Studio Phase (신규)

### Phase 6 — Design Document Generator

| Feature | Test level selection | Test scope | Fixtures / Seed | Mocked vs Real | CI Stage | Cost | Release-blocking | TDD Mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DDK-REQ-022` Requirements Elicitation | Unit primary, Integration secondary | 인터뷰 턴 파싱, 요구사항 추출 정확도, 포맷 검증, 20턴 예산 제어 | 아이디어 입력 fixture, 인터뷰 대화 fixture | fake LLM unit, real interview integration | PR | Medium | Yes | TDD required |
| `DDK-REQ-023` Standard-Compliant Doc Synthesis | Integration primary, Contract secondary | 10개 문서 유형별 표준 구조 검증, 요구사항 추적성, 메타데이터 포함 | 요구사항 목록 fixture, 표준 템플릿 fixture | fake LLM in PR, real LLM dogfood later | PR + Staging | High | Yes | TDD preferred |
| `DDK-REQ-024` Quality Gate & Consistency Check | Unit primary, Integration secondary, Contract secondary | 6축 점수 산출, hard block 감지, 추적성 검증, 보완 권고 생성 | 완전/불완전 패키지 fixture, block 조건 fixture | fake scorer unit, real gate integration | PR + Merge | Medium | Yes | TDD required |

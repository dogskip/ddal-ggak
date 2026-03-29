---
phase: "03-code-generation-normalization"
plan: "01"
subsystem: "code-generator"
tags: ["code-generation", "llm-service", "graph-node", "tdd"]
dependency_graph:
  requires: ["03-00"]
  provides: ["CodeGenerator service", "generate_node adapter"]
  affects: ["src/ddk/services/code_generator.py", "src/ddk/graph/nodes/generate.py"]
tech_stack:
  added: []
  patterns: ["D-05 thin adapter", "node-by-node LLM calls", "FakeLLM key derivation"]
key_files:
  created:
    - src/ddk/services/code_generator.py
    - src/ddk/graph/nodes/generate.py
    - tests/unit/services/test_code_generator.py
  modified: []
decisions:
  - "System prompt starts with 'Generate' → FakeLLM key='generate', no collision with SemanticIntentExtractor key='you'"
  - "One LLM call per node in execution_order (node-by-node, not batched)"
  - "Empty execution_order returns empty GeneratedArtifactSet with 0 LLM calls"
  - "model=claude-3-5-sonnet-20241022, temperature=0.0 (CODEGEN-01 spec)"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_created: 3
---

# Phase 03 Plan 01: CodeGenerator Service + generate_node Summary

## One-liner

CodeGenerator service implementing node-by-node LLM calls (GenerationPlan → GeneratedArtifactSet) with D-05 thin adapter generate_node.

## What Was Built

### Task 1: CodeGenerator service (`src/ddk/services/code_generator.py`)

- `CodeGenerator` class with `generate_all(plan, repo_profile, intent_graph, prompt) → GeneratedArtifactSet`
- One LLM call per `GenerationNode` in `plan.execution_order` (node-by-node, not batched)
- Internal `_GeneratedNodeOutput` pydantic model as per-node LLM output schema
- Empty `execution_order` short-circuits → empty `GeneratedArtifactSet`, 0 LLM calls
- `LLMCallConfig(model="claude-3-5-sonnet-20241022", temperature=0.0, max_tokens=4096)`
- System prompt starts with `"Generate"` → FakeLLM key=`"generate"` (no collision with `"you"` from SemanticIntentExtractor or `"senior"` from GenerationPlanner)
- Populates `file_map`, `generation_trace`, `changed_paths` from LLM responses

### Task 2: generate_node adapter (`src/ddk/graph/nodes/generate.py`)

- Thin D-05 adapter following `plan_node` pattern exactly
- Reads: `state["generation_plan"]`, `state["repo_profile"]`, `state["intent_graph"]`, `state["case_input"].prompt`
- Writes: `{"generated_artifacts": GeneratedArtifactSet, "current_node": "generate"}`
- No LLM: returns `{"terminal_state": "manual-review-required", "error_message": ...}`
- No business logic in adapter layer

### Tests (`tests/unit/services/test_code_generator.py`)

9 tests in 2 test classes:

**TestCodeGenerator** (7 tests):
1. `test_generate_all_returns_artifact_set` — returns `GeneratedArtifactSet` with correct `case_id`
2. `test_one_llm_call_per_node` — 3-node plan → exactly 3 LLM calls
3. `test_empty_plan_returns_empty_artifacts` — empty `execution_order` → empty artifacts, 0 calls
4. `test_file_map_contains_all_paths` — `file_map` keys/values match LLM response
5. `test_generation_trace_has_one_entry_per_node` — trace entry per node processed
6. `test_model_is_claude_sonnet` — model=`claude-3-5-sonnet-20241022`
7. `test_temperature_is_zero` — temperature=0.0

**TestGenerateNode** (2 tests):
8. `test_generate_node_thin_adapter` — reads state, calls generator, returns `generated_artifacts`
9. `test_generate_node_no_llm_returns_error` — `terminal_state=manual-review-required`

## Verification

```
uv run pytest tests/unit/services/test_code_generator.py -v
→ 9 passed

uv run pytest tests/ -q
→ 336 passed

FakeLLM key smoke check:
→ FakeLLM key: generate — OK
```

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — CodeGenerator wires LLM calls directly; no placeholder data.

## Commits

| Hash    | Message                                             |
|---------|-----------------------------------------------------|
| 57ca796 | feat(03-01): CodeGenerator service + generate_node  |

## Self-Check: PASSED

- `src/ddk/services/code_generator.py` — FOUND
- `src/ddk/graph/nodes/generate.py` — FOUND
- `tests/unit/services/test_code_generator.py` — FOUND
- Commit `57ca796` — FOUND
- 336 tests passing — VERIFIED

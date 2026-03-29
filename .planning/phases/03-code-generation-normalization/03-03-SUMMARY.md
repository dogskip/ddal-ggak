---
phase: "03"
plan: "03"
subsystem: graph
tags: [langgraph, builder, integration-tests, e2e, phase3-complete]
dependency_graph:
  requires: ["03-02"]
  provides: ["7-node-graph", "e2e-integration-tests"]
  affects: ["tests/integration", "src/ddk/graph/builder.py"]
tech_stack:
  added: []
  patterns: ["7-node LangGraph pipeline", "FakeLLMAdapter E2E pattern"]
key_files:
  created:
    - tests/integration/test_generation_pipeline.py
  modified:
    - src/ddk/graph/builder.py
    - tests/integration/test_ingestion_pipeline.py
decisions:
  - "D-08 Phase 3 completion: replaced plan→END with plan→generate→normalize→END"
  - "Ingestion pipeline test updated to assert current_node='normalize' (from 'plan')"
  - "test_generation_pipeline.py uses execution_order=['node-btn'] to trigger real LLM calls in both generate and normalize nodes"
metrics:
  duration: "3m18s"
  completed: "2026-03-29"
  tasks: 2
  files: 3
---

# Phase 3 Plan 03: 7-Node Graph + E2E Integration Tests Summary

**One-liner:** Extended 5-node graph to 7-node pipeline (plan→generate→normalize→END) with 5 E2E integration tests using FakeLLMAdapter.

## What Was Built

### Task 1: Update `builder.py` to 7-node graph + fix ingestion pipeline test

**`src/ddk/graph/builder.py`** — Extended from 5-node to 7-node StateGraph:
- Added imports: `generate_node`, `normalize_node`
- Added nodes: `workflow.add_node("generate", ...)`, `workflow.add_node("normalize", ...)`
- Replaced `workflow.add_edge("plan", END)` with chain `plan → generate → normalize → END`
- Updated module docstring to reflect Phase 3 completion

**`tests/integration/test_ingestion_pipeline.py`** — Updated for 7-node pipeline:
- Added `_GENERATED_NODE_RESPONSE` and `_NORMALIZATION_RESPONSE` constants (minimal, not called — empty `execution_order` causes both services to short-circuit)
- Extended `pipeline_fake_llm` fixture with `"generate"` and `"normalize"` keys
- Updated assertion `result["current_node"] == "plan"` → `"normalize"`
- Updated docstring/comments to reflect Phase 3 completion

### Task 2: Create `tests/integration/test_generation_pipeline.py`

5 E2E integration tests in `class TestSevenNodePipeline`:

| Test | Assertion |
|------|-----------|
| `test_seven_node_pipeline_end_to_end` | `result is not None`, `terminal_state is None`, `case_id` preserved |
| `test_pipeline_produces_generated_artifacts` | `generated_artifacts is not None`, `files[0].path == "src/components/Button.tsx"` |
| `test_pipeline_produces_normalization_report` | `normalization_report is not None`, `case_id` matches, `convention_fixes` has 1 entry |
| `test_pipeline_reaches_normalize_node` | `current_node == "normalize"` |
| `test_pipeline_preserves_case_id` | `case_id == sample_input.case_id`, `generated_artifacts.case_id` matches |

Key design: `_GENERATION_PLAN_RESPONSE` includes `execution_order: ["node-btn"]` so `CodeGenerator.generate_all()` makes a real LLM call (→ `generate` key), and `OutputNormalizer.normalize()` also makes a real LLM call (→ `normalize` key) since `files` is non-empty.

## Test Results

| Before | After |
|--------|-------|
| 345 tests | 350 tests |
| 0 failures | 0 failures |

## 7-Node Graph Topology

```
START → intake → repo_scan → intent_extract → design_system → plan → generate → normalize → END
```

Verified with:
```
Nodes: ['__start__', 'intake', 'repo_scan', 'intent_extract', 'design_system', 'plan', 'generate', 'normalize']
7-node graph topology check PASS
```

## Phase 3 Complete ✅

All Phase 3 plans (03-00 through 03-03) complete:
- 03-00: Models + services foundation
- 03-01: CodeGenerator service (CODEGEN-01)
- 03-02: OutputNormalizer service (CODEGEN-02)
- **03-03: 7-node graph + E2E tests (D-08 complete)**

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

Files exist:
- `src/ddk/graph/builder.py` ✅
- `tests/integration/test_ingestion_pipeline.py` ✅
- `tests/integration/test_generation_pipeline.py` ✅

Commit `fcd54a0` exists ✅

Test count: 350 (was 345, +5 new integration tests) ✅

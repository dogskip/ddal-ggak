---
phase: 02-ingestion-analysis
plan: 05
subsystem: graph
tags: [langgraph, graph-assembly, integration-test, DI, wave-3]
dependency_graph:
  requires: [02-02, 02-03, 02-04]
  provides: [5-node-partial-graph, D-08, ingestion-pipeline-E2E]
  affects: [src/ddk/graph/builder.py, src/ddk/graph/nodes/_wrapper.py]
tech_stack:
  added: []
  patterns: [context_schema DI injection via Optional[RunnableConfig], node_wrapper config bridging]
key_files:
  created:
    - tests/integration/test_ingestion_pipeline.py
  modified:
    - src/ddk/graph/builder.py
    - src/ddk/graph/nodes/_wrapper.py
decisions:
  - "Use Optional[RunnableConfig] annotation in node_wrapper (not RunnableConfig | None) because LangGraph KWARGS_CONFIG_KEYS only recognizes the Optional form for runtime config injection"
  - "node_wrapper bridges LangGraph config injection to node kwargs: extracts context from config['configurable'][CONFIG_KEY_RUNTIME].context and passes it as context= kwarg"
  - "Integration test uses package.json with react dependency to avoid LLM supplementation in repo_scan_node (static scan sufficient when framework != 'other')"
metrics:
  duration: ~15m
  completed: 2025-03-28
  tasks_completed: 2
  files_changed: 3
---

# Phase 02 Plan 05: 5-Node Graph Assembly + E2E Integration Test Summary

**One-liner:** 5-node LangGraph partial graph (D-08) wired in builder.py with Optional[RunnableConfig] context bridge in node_wrapper, validated by 4 E2E integration tests using FakeLLMAdapter.

## What Was Built

### Task 1: builder.py — 5-Node Graph Assembly

`src/ddk/graph/builder.py` replaced the Phase 1 placeholder `_start_node` with a 5-node ingestion pipeline:

```
START → intake → repo_scan → intent_extract → design_system → plan → END
```

All 5 nodes are registered via `node_wrapper()` for error boundaries. The existing DI smoke test (3 tests) remains fully backward-compatible.

### Task 2: Integration Test + node_wrapper Fix

**`tests/integration/test_ingestion_pipeline.py`** — 4 integration tests:
- `test_five_node_pipeline` — full E2E, validates repo_profile / intent_graph / generation_plan all non-None
- `test_pipeline_preserves_case_id` — case_id integrity through pipeline
- `test_pipeline_repo_profile_has_framework` — static scan detects 'react' from package.json
- `test_pipeline_generation_plan_has_case_id` — GenerationPlan.case_id injected correctly

**`src/ddk/graph/nodes/_wrapper.py`** — Bug fix (Deviation Rule 1): LangGraph's `KWARGS_CONFIG_KEYS` only recognizes `Optional[RunnableConfig]` annotation (not `RunnableConfig | None` union syntax). With `from __future__ import annotations`, the annotation becomes a string `"RunnableConfig | None"` which is not in LangGraph's recognized types. Fixed by using `Optional[RunnableConfig]` annotation and adding context extraction from `config['configurable'][CONFIG_KEY_RUNTIME].context`.

## Test Counts

| Suite | Before | After |
|-------|--------|-------|
| Unit tests | 248 | 248 |
| Integration tests | 21 | 25 (+4) |
| **Total** | **269** | **273** |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed node_wrapper config annotation for LangGraph DI injection**
- **Found during:** Task 2 (integration test failure debugging)
- **Issue:** `node_wrapper._wrapped` used `RunnableConfig | None` annotation with `from __future__ import annotations`. LangGraph's `KWARGS_CONFIG_KEYS` only recognizes `Optional[RunnableConfig]` for runtime injection — the union-syntax string `"RunnableConfig | None"` was not recognized, so `config` was always `None` in wrapped nodes, breaking context-schema DI entirely.
- **Fix:** Changed annotation to `Optional[RunnableConfig]` from `typing` module; added `CONFIG_KEY_RUNTIME`-based context extraction in `_wrapped` to forward ServiceContainer as `context=` kwarg
- **Files modified:** `src/ddk/graph/nodes/_wrapper.py`
- **Commit:** f9dbf6c

## Commits

| Hash | Message |
|------|---------|
| `1d70261` | feat(02-05): 5-node graph assembly in builder.py |
| `f9dbf6c` | feat(02-05): E2E integration test for ingestion pipeline |

## Self-Check: PASSED

- ✅ `src/ddk/graph/builder.py` — exists
- ✅ `tests/integration/test_ingestion_pipeline.py` — exists
- ✅ `src/ddk/graph/nodes/_wrapper.py` — exists
- ✅ Commit `1d70261` — verified in git log
- ✅ Commit `f9dbf6c` — verified in git log
- ✅ 273 tests pass (`uv run pytest tests/unit tests/integration -x -q`)

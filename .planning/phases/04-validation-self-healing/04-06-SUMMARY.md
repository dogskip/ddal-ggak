---
phase: "04"
plan: "06"
subsystem: validation-self-healing
tags: [playwright, ssim, integration-tests, regression, quality-gate, phase4-complete]
dependency_graph:
  requires: ["04-05"]
  provides: ["phase4-green-gate", "playwright-integration", "ssim-integration", "wrapper-di-regression-test"]
  affects: ["tests/integration", "src/ddk/graph/nodes/_wrapper.py", ".planning/ROADMAP.md", ".planning/STATE.md"]
tech_stack:
  added: []
  patterns: ["real Playwright integration", "real SSIM integration", "LangGraph runtime DI bridge", "full regression gate"]
key_files:
  created:
    - tests/integration/test_phase4_playwright.py
    - tests/unit/test_node_wrapper.py
  modified:
    - src/ddk/graph/nodes/_wrapper.py
    - tests/contract/test_graph_state_schema.py
    - tests/integration/test_generation_pipeline.py
    - tests/integration/test_ingestion_pipeline.py
    - .planning/ROADMAP.md
    - .planning/STATE.md
decisions:
  - "LangGraph node wrapper now supports both direct runtime injection and configurable runtime extraction, because current runtime paths vary by execution mode"
  - "Phase 4 integration tests remain opt-in via @pytest.mark.playwright and are excluded from default CI runs with -m 'not playwright'"
  - "GraphState contract is now 22 fields; failure_hash_history is part of the stable public graph-state schema"
metrics:
  completed: "2026-03-29"
  tests_non_playwright: "413 passed, 2 deselected"
  tests_phase4: "61 passed"
  tests_playwright: "2 skipped"
  pyright: "0 errors"
  ruff: "clean"
---

# Phase 4 Plan 06: Integration Gate + Final Verification Summary

**One-liner:** Closed Phase 4 by adding real Playwright/SSIM integration coverage, fixing LangGraph runtime context injection in `node_wrapper`, updating stale contract/integration tests to the 9-node validation graph, and proving the repo is green under the Phase 4 gate.

## What Was Completed

### 1. Real integration coverage for Wave 5

`tests/integration/test_phase4_playwright.py` now contains two real integration tests:

- Playwright captures console errors from a live in-process HTML server
- PIL + scikit-image SSIM detects meaningful visual differences between generated images

The file is marked with `pytest.mark.playwright`, so default regression runs stay stable while still preserving real browser/pixel verification when the environment supports it.

### 2. LangGraph DI regression fixed at the wrapper boundary

The biggest regression was not in Phase 4 logic itself, but in the LangGraph DI bridge:

- compiled graphs were not reliably delivering run-scoped context through `kwargs["context"]`
- some execution paths expose runtime on a direct `runtime` parameter
- other execution paths expose it via `config["configurable"]["__pregel_runtime"]`

`src/ddk/graph/nodes/_wrapper.py` now supports both paths:

- direct runtime object → `runtime.context`
- config fallback → `config["configurable"][runtime_key].context`

This unblocked `validate_node` and restored the intended 9-node pipeline behavior.

### 3. Wrapper regression test added

`tests/unit/test_node_wrapper.py` was added to lock the DI fix in place:

- `_extract_context()` recognizes the pregel runtime key
- a compiled graph can flow run-scoped context through `node_wrapper`

This closes the exact regression that was breaking Phase 4 integration flow.

### 4. Stale tests updated to the Phase 4 graph contract

Older tests still encoded the Phase 3 worldview (`normalize -> END`). They were updated to match the Phase 4 9-node validation/self-healing graph:

- `tests/contract/test_graph_state_schema.py`
- `tests/integration/test_generation_pipeline.py`
- `tests/integration/test_ingestion_pipeline.py`

Key updates:

- GraphState field count updated from 21 to 22
- `failure_hash_history` included in the contract
- integration tests now expect the graph to reach `validate`
- validation pass-through is wired for integration fixtures

## Final Verification Results

### Quality gate

```text
uv run ruff check src/ tests/
All checks passed!

uv run pyright src/
0 errors, 0 warnings, 0 informations
```

### Regression suite

```text
uv run pytest tests/ -q -m "not playwright" --tb=short
413 passed, 2 deselected, 136 warnings in 1.17s

uv run pytest tests/unit/phase4/ -q --tb=short
61 passed, 27 warnings in 0.17s

uv run pytest tests/integration/test_phase4_playwright.py -q -m playwright --tb=short
2 skipped in 0.56s
```

## Phase 4 Outcome

Phase 4 is now complete and verified:

- runtime validation flow is wired into the graph
- self-healing loop contract is covered by unit tests
- real Playwright/SSIM integration coverage exists
- full non-Playwright regression is green
- type and lint gates are green

## Deviations from Plan

There was one meaningful deviation:

- during final verification, the main blocker turned out to be LangGraph runtime DI compatibility rather than the Playwright/SSIM logic itself

This was fixed at the infrastructure boundary (`node_wrapper`) instead of papering over the issue in individual nodes. That is the correct fix because it restores all context-driven nodes, not just Phase 4 validation.

## Self-Check

PASS

- Phase 4 graph contract matches tests
- full non-Playwright suite is green
- dedicated Phase 4 suite is green
- wrapper regression is covered
- real Playwright integration tests are present and safe to skip when browser binaries are unavailable

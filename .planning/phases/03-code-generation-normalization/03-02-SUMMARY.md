---
phase: "03"
plan: "02"
subsystem: code-generation
tags: [output-normalizer, normalization, llm-haiku, graph-node, drift-score]
dependency_graph:
  requires: ["03-01"]
  provides: ["OutputNormalizer.normalize()", "normalize_node"]
  affects: ["graph pipeline", "normalization_report state", "generated_artifacts state"]
tech_stack:
  added: []
  patterns: ["D-05 thin adapter", "LLM-based normalization (haiku)", "compute_drift_score"]
key_files:
  created:
    - src/ddk/services/output_normalizer.py
    - src/ddk/graph/nodes/normalize.py
    - tests/unit/services/test_output_normalizer.py
  modified: []
decisions:
  - "LLM-based (haiku) normalization — NOT rule-based AST, per 16-prompt-design.md §6"
  - "System prompt starts with 'Normalize' for unique FakeLLM key='normalize'"
  - "drift_score_after computed from unresolved fixes (description in unresolved_drift list)"
  - "normalize_node guards None generated_artifacts with terminal_state=manual-review-required"
metrics:
  duration_minutes: 8
  completed_date: "2026-03-29T05:16:31Z"
  tasks_completed: 2
  files_created: 3
  files_modified: 0
  tests_before: 336
  tests_after: 345
  commit: "dbdb002"
---

# Phase 03 Plan 02: OutputNormalizer Service + normalize_node Summary

**One-liner:** LLM-based (haiku, temp=0.0) convention normalizer with drift score computation + D-05 thin graph adapter.

## What Was Built

Implemented the `OutputNormalizer` service (CODEGEN-02) and its thin graph adapter `normalize_node`, completing Wave 2 of Phase 3.

### OutputNormalizer (`src/ddk/services/output_normalizer.py`)

- `normalize(artifacts, repo_profile) -> tuple[NormalizationReport, GeneratedArtifactSet]`
- Calls LLM once per normalize invocation (not per file) using `claude-3-haiku-20240307` at `temperature=0.0`
- System prompt starts with **"Normalize"** — unique FakeLLM key `"normalize"` (no collision with existing keys)
- Empty `artifacts.files` short-circuits: returns empty `NormalizationReport` + unchanged artifacts, 0 LLM calls
- `drift_score_before` = `compute_drift_score(all convention_fixes from LLM)`
- `drift_score_after` = `compute_drift_score(fixes whose description appears in unresolved_drift)`
- Applies `patched_files` dict from LLM response to update file contents when provided
- Internal `_NormalizationLLMOutput` schema: `convention_fixes`, `unresolved_drift`, `patched_files`

### normalize_node (`src/ddk/graph/nodes/normalize.py`)

- D-05 thin adapter — identical structure to `generate_node`
- Guards: `llm is None` → `terminal_state="manual-review-required"`
- Guards: `state["generated_artifacts"] is None` → `terminal_state="manual-review-required"` (Pitfall 4)
- Returns `{normalization_report, generated_artifacts (patched), current_node="normalize"}`

## Test Results

| Metric | Value |
|--------|-------|
| Tests before | 336 |
| Tests after | 345 |
| New tests added | 9 |
| All tests passing | ✅ |

### Tests in `test_output_normalizer.py`

**`TestOutputNormalizer` (7 tests):**
1. `test_normalize_returns_tuple` — isinstance check for `(NormalizationReport, GeneratedArtifactSet)`
2. `test_normalize_case_id_matches` — `report.case_id == artifacts.case_id`
3. `test_drift_score_before_positive` — `drift_score_before > 0` when fixes present
4. `test_drift_score_after_lte_before` — `drift_score_after <= drift_score_before`
5. `test_empty_artifacts_shortcircuits` — no LLM call, empty report, same artifacts object returned
6. `test_model_is_haiku` — `config.model == "claude-3-haiku-20240307"`
7. `test_temperature_is_zero` — `config.temperature == 0.0`

**`TestNormalizeNode` (2 tests):**
8. `test_normalize_node_thin_adapter` — success path returns normalization_report + patched generated_artifacts + current_node="normalize"
9. `test_normalize_node_guards_none_artifacts` — None generated_artifacts → terminal_state="manual-review-required"

## Key Invariants Verified

```
FakeLLM key: normalize — OK        (system prompt starts with "Normalize")
compute_drift_score([must-fix]) = 2.0 — OK
Full suite: 345 passed in 0.93s
```

## FakeLLM Key Map (complete after Wave 2)

| Key | Service |
|-----|---------|
| `"you"` | SemanticIntentExtractor |
| `"analyze"` | DesignSystemInferencer |
| `"senior"` | GenerationPlanner |
| `"generate"` | CodeGenerator (Wave 1) |
| `"normalize"` | OutputNormalizer (Wave 2) ← |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all core functionality is wired. `patched_files` handling is complete (LLM provides patches, they are applied to the artifact set).

## Self-Check: PASSED

- `src/ddk/services/output_normalizer.py` — FOUND
- `src/ddk/graph/nodes/normalize.py` — FOUND
- `tests/unit/services/test_output_normalizer.py` — FOUND
- Commit `dbdb002` — FOUND (345 passed)

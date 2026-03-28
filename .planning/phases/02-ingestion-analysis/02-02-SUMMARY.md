---
phase: 02-ingestion-analysis
plan: "02"
subsystem: services/ingestion
tags: [intake, repo-scan, static-analysis, llm-supplement, tdd, langraph-nodes]
dependency_graph:
  requires: ["02-01"]
  provides: ["intake-processor", "repo-convention-scanner", "intake-node", "repo-scan-node"]
  affects: ["02-05-builder"]
tech_stack:
  added: []
  patterns:
    - "TDD (RED→GREEN) with asyncio_mode=auto"
    - "Thin adapter node pattern (D-05): node reads state → calls service → writes state"
    - "Static-first + LLM supplement (D-07): haiku only when framework=other"
    - "SHA256[:16] image hash computation"
key_files:
  created:
    - src/ddk/services/intake_processor.py
    - src/ddk/graph/nodes/intake.py
    - tests/unit/services/test_intake_processor.py
    - src/ddk/graph/nodes/repo_scan.py
    - tests/unit/services/test_repo_convention_scanner.py
  modified:
    - src/ddk/services/repo_convention_scanner.py
decisions:
  - "D-05 enforced: intake_node and repo_scan_node contain zero business logic — pure state I/O adapters"
  - "D-07 enforced: _needs_llm_supplement() returns True only when framework=='other' (not default PascalCase check from plan template — that would always trigger LLM)"
  - "FakeLLMAdapter key='you' for system prompts starting with 'You are a senior...'"
  - "Parallel wave isolation: staged only own files, left other wave files unstaged"
metrics:
  duration: "13m"
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_changed: 6
---

# Phase 02 Plan 02: IntakeProcessor + RepoConventionScanner Summary

**One-liner:** SHA256-based image intake validation + static-first repo scanner with haiku LLM fallback for unknown frameworks.

## Objective Achieved

Implemented both pipeline entry-point services (INGEST-02, INGEST-03):
- `IntakeProcessor.process()` validates image paths exist and computes SHA256[:16] hashes
- `RepoConventionScanner.scan()` statically parses `package.json`/`tsconfig.json`/lock files; calls Claude haiku only when `framework="other"`
- Two thin adapter nodes (`intake_node`, `repo_scan_node`) per D-05 — no business logic
- 21 unit tests passing using `FakeLLMAdapter`

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | IntakeProcessor + intake_node + tests | a6f2945 | `intake_processor.py`, `nodes/intake.py`, `test_intake_processor.py` |
| 2 | RepoConventionScanner + repo_scan_node + tests | bbf4cb6 | `repo_convention_scanner.py`, `nodes/repo_scan.py`, `test_repo_convention_scanner.py` |

## Decisions Made

### D-05 Thin Node Pattern — Strictly Enforced
Both nodes are pure state I/O adapters:
```python
async def intake_node(state, **kwargs):
    processor = IntakeProcessor()
    validated_input, image_hashes = await processor.process(state["case_input"])
    return {"case_input": validated_input, "current_node": "intake"}
```
Zero business logic in nodes.

### D-07 LLM Trigger Condition Corrected
The plan template showed `_needs_llm_supplement()` returning True for `framework == "other" or naming_rules.component_pattern == "PascalCase"`. Since `"PascalCase"` is the default, this would trigger LLM on every call — contradicting D-07. Implemented as:
```python
def _needs_llm_supplement(self, profile: RepoProfile) -> bool:
    return profile.framework == "other"
```
This matches D-07 spec: "LLM called only when static analysis is insufficient."

### FakeLLMAdapter Key Extraction
`RepoConventionScanner._llm_supplement()` system prompt starts with `"You are a senior..."` → key = `"you"`. Tests register `responses={"you": json.dumps({...})}`.

## Test Results

```
tests/unit/services/test_intake_processor.py   6 passed
tests/unit/services/test_repo_convention_scanner.py  15 passed
Total: 21 passed, 0 failed
```

Full unit suite (excluding cross-wave files from other parallel agents): 213 passed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `_needs_llm_supplement` condition**
- **Found during:** Task 2 implementation review
- **Issue:** Plan template had `or profile.naming_rules.component_pattern == "PascalCase"` which is always True (PascalCase is default), causing LLM to always be called — contradicts D-07
- **Fix:** Simplified to `return profile.framework == "other"` per D-07 spec in context notes
- **Files modified:** `src/ddk/services/repo_convention_scanner.py`
- **Commit:** bbf4cb6

### Out-of-Scope Issue (Deferred)

`tests/unit/services/test_design_system_inferencer.py` (created by parallel wave agent 02-03/04) imports `_SYSTEM_PROMPT` from `ddk.services.design_system_inferencer` which doesn't exist in the stub yet. This import error fails when running `uv run pytest tests/ -x -q`. Not in scope for this plan — will be resolved when 02-03/02-04 implements their service.

## Known Stubs

None — all stubs fully replaced with working implementations.

## Self-Check

### Files Exist
- `src/ddk/services/intake_processor.py` ✓
- `src/ddk/graph/nodes/intake.py` ✓
- `tests/unit/services/test_intake_processor.py` ✓
- `src/ddk/services/repo_convention_scanner.py` ✓
- `src/ddk/graph/nodes/repo_scan.py` ✓
- `tests/unit/services/test_repo_convention_scanner.py` ✓

### Commits Exist
- `a6f2945` — Task 1 ✓
- `bbf4cb6` — Task 2 ✓

## Self-Check: PASSED

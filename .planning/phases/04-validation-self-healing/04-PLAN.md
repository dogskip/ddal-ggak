---
phase: 04-validation-self-healing
plan: 00
type: execute
wave: 0
depends_on: []
files_modified: []
autonomous: true
requirements: [VALID-01, VALID-02, VALID-03, VALID-04, VALID-05, VALID-07]

must_haves:
  truths:
    - "Generated code runs inside a git-worktree sandbox and produces a RuntimeValidationReport with build/type/lint/runtime fields"
    - "Playwright captures browser console errors and failed network requests with correlation IDs"
    - "SSIM comparison of reference vs generated screenshots produces a VisualRegressionReport with score and mismatch regions"
    - "All failures carry a stable FAILURE_TAXONOMY ID (FT-BUILD-*, FT-TYPE-*, FT-LINT-*, FT-RUNTIME-*, FT-VISUAL-*, FT-ASYNC-*)"
    - "AutoFixPlanner applies the correct one of 9 rules (R-01~R-08 deterministic, R-09 LLM) and produces file patches"
    - "The validate→autofix back-edge loop respects 3-retry budget and detects oscillation via (taxonomy_id, file_path) hash — not UUID"
    - "Each fix attempt creates a git checkpoint ref refs/ddk/fix/{case_id}/attempt-{n}; failed attempts roll back automatically"
    - "Full pass case exits via 'pass' edge; exhausted/oscillating exits via 'exhausted' edge with terminal_state='manual-review-required'"
  artifacts:
    - path: "src/ddk/services/failure_classifier.py"
      provides: "FAILURE_TAXONOMY mapping — pure logic, no I/O"
      exports: ["FailureClassifier"]
    - path: "src/ddk/services/rollback_controller.py"
      provides: "git checkpoint create/rollback — wraps GitAdapter"
      exports: ["RollbackController"]
    - path: "src/ddk/services/runtime_validator.py"
      provides: "Sandbox orchestration: build/typecheck/lint/playwright/SSIM"
      exports: ["RuntimeValidator"]
    - path: "src/ddk/services/auto_fix_planner.py"
      provides: "9-rule hybrid patch planner (R-01~R-08 deterministic, R-09 LLM)"
      exports: ["AutoFixPlanner"]
    - path: "src/ddk/graph/nodes/validate.py"
      provides: "Thin adapter: state → RuntimeValidator → state"
      exports: ["validate_node"]
    - path: "src/ddk/graph/nodes/autofix.py"
      provides: "Thin adapter: state → AutoFixPlanner → state, decrements budget"
      exports: ["autofix_node"]
    - path: "src/ddk/graph/router.py"
      provides: "route_after_validate() pure function — pass/fix_available/exhausted"
      exports: ["route_after_validate"]
    - path: "src/ddk/adapters/playwright_browser.py"
      provides: "FailedRequestEntry dataclass + get_failed_requests() protocol method (additive)"
      contains: "FailedRequestEntry"
    - path: "src/ddk/graph/state.py"
      provides: "failure_hash_history: list[int] field (additive-only)"
      contains: "failure_hash_history"
    - path: "tests/fakes/fake_build_runner.py"
      provides: "FakeBuildRunner(returncode, stderr)"
    - path: "tests/fakes/fake_ssim_adapter.py"
      provides: "FakeSSIMAdapter(ssim_score, diff_path)"
  key_links:
    - from: "src/ddk/graph/nodes/validate.py"
      to: "src/ddk/services/runtime_validator.py"
      via: "RuntimeValidator(sandbox, build_runner, playwright, screenshot_diff, git)"
      pattern: "RuntimeValidator"
    - from: "src/ddk/graph/nodes/autofix.py"
      to: "src/ddk/services/auto_fix_planner.py"
      via: "AutoFixPlanner(llm=container.llm)"
      pattern: "AutoFixPlanner"
    - from: "src/ddk/graph/builder.py"
      to: "src/ddk/graph/router.py"
      via: "add_conditional_edges('validate', route_after_validate, {...})"
      pattern: "add_conditional_edges"
    - from: "src/ddk/graph/builder.py"
      to: "src/ddk/graph/nodes/autofix.py"
      via: "add_edge('autofix', 'validate')  # back-edge"
      pattern: "add_edge.*autofix.*validate"
    - from: "src/ddk/graph/router.py"
      to: "src/ddk/graph/state.py"
      via: "hash(frozenset((f.taxonomy_id, f.file_path or '') for f in failures))"
      pattern: "taxonomy_id.*file_path"
---

# Phase 4 Master Plan: Validation & Self-Healing

## Wave Structure & Dependency Graph

```
Wave 0  ──────────────────────────────────────────────────────────────────
  04-01  Foundations
         • pyproject.toml: add scikit-image, Pillow, playwright, pytest-playwright
         • uv sync + playwright install chromium
         • GraphState: add failure_hash_history: list[int]  (additive)
         • playwright_browser.py: add FailedRequestEntry + get_failed_requests()  (additive)
         • tests/fakes/fake_build_runner.py  (new)
         • tests/fakes/fake_ssim_adapter.py  (new)
         • tests/unit/phase4/__init__.py  (new)
         • Smoke: uv run pytest → all 350 existing tests still pass

Wave 1  ──────────────────────────────────────────────────────────────────  depends: Wave 0
  04-02  FailureClassifier + RollbackController  (pure logic, no I/O, parallelizable)
         • TDD: test_failure_classifier.py → failure_classifier.py
         • TDD: test_rollback_controller.py → rollback_controller.py

Wave 2  ──────────────────────────────────────────────────────────────────  depends: Wave 1
  04-03  RuntimeValidator  (sandbox orchestration, VALID-01/02/03)
         • TDD: test_runtime_validator.py → runtime_validator.py

Wave 3  ──────────────────────────────────────────────────────────────────  depends: Wave 1
  04-04  AutoFixPlanner  (9-rule hybrid, VALID-04)
         • TDD: test_auto_fix_planner.py → auto_fix_planner.py

Wave 4  ──────────────────────────────────────────────────────────────────  depends: Wave 2 + Wave 3
  04-05  Graph Integration
         • TDD: test_validate_node.py + test_autofix_node.py + test_router.py + test_builder_phase4.py
         • validate.py + autofix.py nodes (thin adapters, D-05)
         • router.py (route_after_validate — BUG FIX: taxonomy_id+file_path hash)
         • builder.py: add nodes + conditional_edges + back-edge
         • context.py: add runtime_validator/auto_fix_planner/failure_classifier/rollback_controller fields

Wave 5  ──────────────────────────────────────────────────────────────────  depends: Wave 4
  04-06  Integration Tests
         • tests/integration/test_phase4_playwright.py  (@pytest.mark.playwright)
         • Real Playwright + simple HTML dev server
         • Real PIL + scikit-image SSIM comparison
         • Final: uv run pytest -m "not playwright" → 350+ tests pass
```

## Dependency Graph

```
04-01 (Wave 0: Foundations)
  └─► 04-02 (Wave 1: FailureClassifier + RollbackController)
        └─► 04-03 (Wave 2: RuntimeValidator)
        │         └─► 04-05 (Wave 4: Graph Integration)
        └─► 04-04 (Wave 3: AutoFixPlanner)            │
                    └──────────────────────────────────┘
                                                   └─► 04-06 (Wave 5: Integration)
```

Note: 04-03 and 04-04 may execute in parallel (both depend only on 04-02 Wave 1 output).

## Requirement Coverage

| Plan  | Requirements |
|-------|-------------|
| 04-01 | Infrastructure for all (no direct req, enables VALID-01~07) |
| 04-02 | VALID-05 (FailureClassifier), VALID-07 (RollbackController) |
| 04-03 | VALID-01 (sandbox build/lint/typecheck), VALID-02 (Playwright), VALID-03 (SSIM) |
| 04-04 | VALID-04 (AutoFixPlanner 9 rules) |
| 04-05 | VALID-04 (loop), VALID-01~07 (graph wiring) |
| 04-06 | VALID-02 (real Playwright), VALID-03 (real SSIM) |

## Critical Bug Notes

### BUG: Oscillation hash uses UUID (CONTEXT.md line 38) — MUST FIX
```python
# ❌ WRONG (CONTEXT.md original — UUIDs regenerated each run → always different hash)
cur_hash = hash(frozenset(failure.id for failure in failures))

# ✅ CORRECT (stable: same errors = same hash across runs)
cur_hash = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in failures))
```
This fix must appear in:
- `src/ddk/graph/router.py` (route_after_validate)
- `src/ddk/graph/nodes/validate.py` (appending to failure_hash_history)
- All related tests

## TDD Mandate
Every wave: Red → Green → Refactor
1. **Red**: Create stub file with `raise NotImplementedError` → `uv run pytest tests/unit/phase4/` FAIL
2. **Green**: Implement minimal logic → all tests pass
3. **Refactor**: `uv run pyright src/` (0 errors strict), `uv run ruff check --fix src/`

## Additive-Only Policy
- `GraphState`: add `failure_hash_history: list[int]` — DO NOT rename/delete any existing field
- `PlaywrightAdapter`: add `FailedRequestEntry` + `get_failed_requests()` — DO NOT change existing methods
- `ServiceContainer`: add 4 service fields — DO NOT rename/delete existing fields
- Models: DO NOT modify `FailureRecord`, `RuntimeValidationReport`, `VisualRegressionReport`, `FixAttempt`

---
phase: "03"
plan: "00"
subsystem: models
tags: [models, pydantic, design-spec-alignment, additive, tdd]
dependency_graph:
  requires: []
  provides:
    - GeneratedArtifactSet with schema_version/changed_paths/trace (12-data-models.md §4)
    - GeneratedFile with is_new/original_content (12-data-models.md §4)
    - NormalizationReport with convention_fixes/drift_score_before/drift_score_after/unresolved_drift (12-data-models.md §5)
    - ConventionFix with fix_type/severity/before/after (12-data-models.md §5)
    - NormalizationReport.compute_drift_score() static method
  affects:
    - Wave 1 (CodeGenerator) — depends on GeneratedArtifactSet.schema_version, changed_paths, trace
    - Wave 2 (OutputNormalizer) — depends on NormalizationReport.convention_fixes, drift_score_before/after
tech_stack:
  added: []
  patterns:
    - Additive-only model extension (all new fields have defaults, zero breaking changes)
    - Pydantic Field(default_factory=list/dict) to prevent mutable default sharing
    - @staticmethod on Pydantic model for pure computation (compute_drift_score)
    - TDD RED→GREEN cycle with explicit float() cast for empty-sum edge case
key_files:
  created:
    - tests/unit/models/test_generation_alignment.py
    - tests/unit/models/test_normalization_alignment.py
  modified:
    - src/ddk/models/generation.py
    - src/ddk/models/normalization.py
decisions:
  - "Additive-only policy: new fields placed after existing fields with explicit default values — existing tests unaffected"
  - "float() cast in compute_drift_score: sum([]) returns int 0, not float 0.0 — explicit cast ensures isinstance(result, float) contract"
  - "kept fixes field alongside convention_fixes in NormalizationReport for backward compatibility with existing tests"
metrics:
  duration: "3m"
  completed_date: "2026-03-29"
  tasks_completed: 2
  files_modified: 4
---

# Phase 03 Plan 00: Model Alignment (GeneratedArtifactSet + NormalizationReport) Summary

**One-liner:** Additive alignment of `GeneratedArtifactSet`/`GeneratedFile` and `NormalizationReport`/`ConventionFix` with `docs/design/12-data-models.md` spec, including `compute_drift_score()` with severity weights.

## What Was Built

Aligned four Pydantic models with the canonical design spec (`docs/design/12-data-models.md`) using strictly additive field additions. All new fields carry default values so zero existing constructors break.

### generation.py changes

**`GeneratedFile`** — 2 new fields:
- `is_new: bool = False`
- `original_content: str | None = None`

**`GeneratedArtifactSet`** — 3 new fields + `Any` import:
- `schema_version: str = "1.0"`
- `changed_paths: list[str] = Field(default_factory=list)`
- `trace: dict[str, Any] = Field(default_factory=dict)`

### normalization.py changes

**`ConventionFix`** — 4 new fields:
- `fix_type: Literal[7 types] = "naming"`
- `severity: Literal["must-fix","should-fix","nice-to-have"] = "must-fix"`
- `before: str | None = None`
- `after: str | None = None`

**`NormalizationReport`** — 4 new fields + 1 static method:
- `convention_fixes: list[ConventionFix] = Field(default_factory=list)`
- `drift_score_before: float = Field(default=0.0, ge=0.0, le=10.0)`
- `drift_score_after: float = Field(default=0.0, ge=0.0, le=10.0)`
- `unresolved_drift: list[str] = Field(default_factory=list)`
- `compute_drift_score(fixes) -> float` — must-fix=2.0, should-fix=1.0, nice-to-have=0.5, cap=10.0

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| All tests | 286 | 327 | +41 new (15 generation + 26 normalization) |
| Failures | 0 | 0 | 0 regressions |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 (generation) | b524e01 | feat(03-00): align GeneratedArtifactSet + GeneratedFile with design spec |
| Task 2 (normalization) | d4f8730 | feat(03-00): align NormalizationReport + ConventionFix with design spec |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `compute_drift_score` empty-list return type**
- **Found during:** Task 2 GREEN phase (test_is_static_method)
- **Issue:** `sum([])` returns Python `int` 0, not `float` 0.0. The test `isinstance(score, float)` failed.
- **Fix:** Added explicit `float()` cast: `return float(min(raw, 10.0))`
- **Files modified:** `src/ddk/models/normalization.py`
- **Commit:** d4f8730 (included in same task commit)

## Known Stubs

None — all new fields are properly typed with defaults. No data flows from stubs to UI. No placeholder values.

## Self-Check: PASSED

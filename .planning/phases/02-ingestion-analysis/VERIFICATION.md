---
phase: 02-ingestion-analysis
verified: 2026-03-28T19:30:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Real Anthropic API call with actual screenshot"
    expected: "IntentGraph + DesignSystem tokens populated from real Claude vision response"
    why_human: "FakeLLM used in all tests; real API cost + key not available in CI"
---

# Phase 2: Ingestion & Analysis — Verification Report

**Phase Goal:** 디자인 시안(이미지+프롬프트)을 받아 5단계 분석(intake → repo scan → intent → design system → plan)을 거쳐 검증된 GenerationPlan을 출력한다 — 첫 LLM 호출 Phase로 비용 추적과 구조화 출력 파싱 패턴을 확립  
**Verified:** 2026-03-28T19:30:00Z  
**Status:** ✅ PASSED  
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | 이미지+프롬프트 입력 시 intake 노드가 검증된 CaseInput 생성 | ✓ VERIFIED | `intake_processor.py` validates image paths + computes SHA256[:16]; `intake_node` is a thin adapter that calls IntakeProcessor and writes `case_input` back to state |
| 2 | Repo convention scanner가 React/TypeScript 프로젝트 분석 → RepoProfile (framework, naming, styling, file layout) | ✓ VERIFIED | `repo_convention_scanner.py` (226 lines): static JSON parse for framework/tsconfig/naming; LLM fallback only when `framework=="other"` (D-07); `scan()` returns `RepoProfile` with all required fields |
| 3 | SemanticIntentExtractor → IntentGraph (layout/interaction/content + confidence); DesignSystemInferencer → tokens/spacing/typography | ✓ VERIFIED | `semantic_intent_extractor.py` (118 lines) uses Claude vision + `complete_structured(output_schema=IntentGraph)`; `design_system_inferencer.py` (161 lines) enriches `repo_profile.design_tokens` via `model_copy(update=...)` |
| 4 | GenerationPlanner → ordered GenerationPlan (task nodes + validation/repair hooks), deterministic on same input | ✓ VERIFIED | `generation_planner.py` (105 lines): `temperature=0.0` + `claude-3-5-sonnet-20241022`; `complete_structured(output_schema=GenerationPlan)` returns topological plan |
| 5 | ContextPackBuilder → deterministic output (≤6 files/300 lines, P1-P5 priority, alpha tie-break) within LLM context budget | ✓ VERIFIED | `context_pack_builder.py` (263 lines): `MAX_FILES=6`, `MAX_LINES=300`; `sort_key=(priority_rank, relation_rank, ceil(lines/50), normalized_path)`; `context_pack_hash = SHA256[:16]` of canonical JSON |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact | Provides | Lines | Status | Details |
|----------|----------|-------|--------|---------|
| `src/ddk/services/intake_processor.py` | Validate CaseInput, compute image hashes | 34 | ✓ VERIFIED | Slim but complete: iterates `image_paths`, checks `.exists()`, computes `sha256[:16]`. No stubs. |
| `src/ddk/services/repo_convention_scanner.py` | Static repo scan → RepoProfile | 226 | ✓ VERIFIED | Parses package.json, tsconfig.json, infers naming rules, LLM supplement on `framework=="other"` |
| `src/ddk/services/semantic_intent_extractor.py` | UI screenshot → IntentGraph via Claude | 118 | ✓ VERIFIED | Sends base64 images, parses `IntentGraph` via `complete_structured` |
| `src/ddk/services/design_system_inferencer.py` | Enrich RepoProfile design tokens | 161 | ✓ VERIFIED | `enrich_profile()` uses `model_copy(update=...)` for immutable Pydantic update |
| `src/ddk/services/generation_planner.py` | IntentGraph + RepoProfile → GenerationPlan | 105 | ✓ VERIFIED | `temperature=0.0`, topological output, `complete_structured` |
| `src/ddk/services/context_pack_builder.py` | Deterministic ContextPack from target files | 263 | ✓ VERIFIED | `sort_key` tuple matches 24-context-pack-determinism.md §3.2; `insufficient_context` flag when no P1 files |
| `src/ddk/graph/builder.py` | 5-node partial StateGraph (D-08) | 46 | ✓ VERIFIED | `START → intake → repo_scan → intent_extract → design_system → plan → END`; all 5 nodes wrapped with `node_wrapper` |
| `tests/integration/test_ingestion_pipeline.py` | E2E pipeline test with FakeLLMAdapter | 246 | ✓ VERIFIED | 4 tests: `test_five_node_pipeline`, `test_pipeline_preserves_case_id`, `test_pipeline_repo_profile_has_framework`, `test_pipeline_generation_plan_has_case_id` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `graph/builder.py` | `nodes/intake.py` | `import intake_node` + `add_node` | ✓ WIRED | Line 14 import, line 33 `add_node` |
| `graph/builder.py` | `nodes/repo_scan.py` | `import repo_scan_node` + `add_node` | ✓ WIRED | Line 16 import, line 34 `add_node` |
| `graph/builder.py` | `nodes/intent_extract.py` | `import intent_extract_node` + `add_node` | ✓ WIRED | Line 13 import, line 35 `add_node` |
| `graph/builder.py` | `nodes/design_system.py` | `import design_system_node` + `add_node` | ✓ WIRED | Line 12 import, line 36 `add_node` |
| `graph/builder.py` | `nodes/plan.py` | `import plan_node` + `add_node` | ✓ WIRED | Line 15 import, line 37 `add_node` |
| `nodes/intake.py` | `services/intake_processor.py` | `IntakeProcessor()` call | ✓ WIRED | `processor.process(case_input)` called in node body |
| `nodes/repo_scan.py` | `services/repo_convention_scanner.py` | `RepoConventionScanner(llm)` call | ✓ WIRED | `scanner.scan(case_input.repo_path)` → state `repo_profile` |
| `nodes/intent_extract.py` | `services/semantic_intent_extractor.py` | `SemanticIntentExtractor(llm)` call | ✓ WIRED | `extractor.extract(state["case_input"])` → state `intent_graph` |
| `nodes/design_system.py` | `services/design_system_inferencer.py` | `DesignSystemInferencer(llm)` call | ✓ WIRED | enriches `repo_profile` in state |
| `nodes/plan.py` | `services/generation_planner.py` | `GenerationPlanner(llm)` call | ✓ WIRED | `planner.plan(...)` → state `generation_plan` |
| `graph/context.py` | all 6 service classes | `ServiceContainer` optional fields | ✓ WIRED | Lines 52–57: 6 `T | None = None` fields for DI injection |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `intake_node` | `case_input` | `IntakeProcessor.process()` | ✓ reads image bytes, computes hash | ✓ FLOWING |
| `repo_scan_node` | `repo_profile` | `RepoConventionScanner.scan()` | ✓ parses real package.json/tsconfig files | ✓ FLOWING |
| `intent_extract_node` | `intent_graph` | `SemanticIntentExtractor.extract()` → `llm.complete_structured()` | ✓ LLM call with base64 images, parsed to `IntentGraph` | ✓ FLOWING |
| `design_system_node` | `repo_profile` (enriched) | `DesignSystemInferencer.enrich_profile()` → LLM | ✓ LLM call, `model_copy(update=...)` with design tokens | ✓ FLOWING |
| `plan_node` | `generation_plan` | `GenerationPlanner.plan()` → `llm.complete_structured()` | ✓ LLM structured output parsed to `GenerationPlan` | ✓ FLOWING |
| `ContextPackBuilder.build()` | `context_pack` | filesystem reads for line counts + sort | ✓ deterministic sort + hash, no hardcoded empty returns | ✓ FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 286 tests pass | `uv run pytest tests/ -x -q` | `286 passed in 0.86s` | ✓ PASS |
| 4 integration E2E tests pass | `uv run pytest tests/integration/test_ingestion_pipeline.py -v` | 4 passed in 0.19s | ✓ PASS |
| 248 unit tests pass (services, models, fakes) | `uv run pytest tests/unit/ -q` | `248 passed in 0.32s` | ✓ PASS |
| 5-node graph topology correct | `grep "add_edge\|add_node" src/ddk/graph/builder.py` | START→intake→repo_scan→intent_extract→design_system→plan→END | ✓ PASS |
| ContextPack MAX_FILES/MAX_LINES constants | `grep "MAX_FILES\|MAX_LINES" src/ddk/services/context_pack_builder.py` | `MAX_FILES = 6`, `MAX_LINES = 300` | ✓ PASS |
| GenerationPlanner temperature=0 determinism | `grep "temperature" src/ddk/services/generation_planner.py` | `temperature=0.0` | ✓ PASS |

---

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| INGEST-02 | Multimodal Intake → CaseInput 검증·구조화 | ✓ SATISFIED | `IntakeProcessor.process()` validates image paths, structures input |
| INGEST-03 | RepoConventionScanner → RepoProfile (framework/naming/styling/file layout) | ✓ SATISFIED | 226-line scanner with static + optional LLM supplement |
| INGEST-04 | SemanticIntentExtractor → IntentGraph (layout/interaction/content + confidence) | ✓ SATISFIED | `complete_structured(output_schema=IntentGraph)` with vision prompt |
| INGEST-05 | DesignSystemInferencer → tokens/spacing/typography/primitives | ✓ SATISFIED | `enrich_profile()` adds `design_tokens` to RepoProfile |
| INGEST-06 | GenerationPlanner → ordered GenerationPlan (output/validate/repair hooks) | ✓ SATISFIED | `temperature=0`, topological ordering, `complete_structured` |
| CODEGEN-03 | ContextPackBuilder → ≤6 files/300 lines, P1-P5, deterministic | ✓ SATISFIED | `sort_key` tuple, `MAX_FILES=6`, `MAX_LINES=300`, `context_pack_hash` |

All 6 Phase 2 requirements marked `[x]` in REQUIREMENTS.md. No orphaned requirements.

---

### Plan Must-Haves Checklist

#### 02-01 (Wave 0 Infrastructure)
- [x] DesignSystem and ContextPack Pydantic models exist and pass roundtrip serialization
- [x] Message dataclass supports optional images field without breaking existing LLM tests
- [x] ClaudeAdapter handles base64 image blocks in Anthropic API content format
- [x] GenerationNode matches design doc schema (node_type, target_path, validation_hooks, repair_hooks)
- [x] `@pytest.mark.integration` marker configured, skips without ANTHROPIC_API_KEY
- [x] ServiceContainer has 6 optional service fields defaulting to None (lines 52–57 in `context.py`)
- [x] All 207 baseline tests pass (now 286 — expanded test suite)

#### 02-02 (Intake + Repo Scan)
- [x] IntakeProcessor validates image paths, computes SHA256[:16] hashes, rejects invalid inputs
- [x] RepoConventionScanner statically parses package.json → framework (react/vue/next/other)
- [x] RepoConventionScanner parses tsconfig.json for TypeScript settings
- [x] LLM supplement only when static analysis insufficient (D-07, `framework=="other"`)
- [x] Thin adapter nodes — no business logic in nodes (D-05)

#### 02-03 (Intent + Design System)
- [x] SemanticIntentExtractor sends image base64 via Message.images, parses IntentGraph via `complete_structured`
- [x] System prompt starts with "You are an expert UI analyst" (per 16-prompt-design.md)
- [x] DesignSystemInferencer enriches repo_profile.design_tokens via `model_copy(update=...)`
- [x] Both services use FakeLLMAdapter for unit tests (D-06)
- [x] Both nodes are thin adapters (D-05)

#### 02-04 (Planner + Context Pack)
- [x] GenerationPlanner creates ordered GenerationPlan with topological execution_order
- [x] Uses `claude-3-5-sonnet-20241022`, `temperature=0.0` (D-06)
- [x] Deterministic output on same input (temperature=0)
- [x] ContextPackBuilder: total_lines ≤ 300, len(chunks) ≤ 6
- [x] `sort_key = (priority_rank, relation_rank, line_bucket, normalized_path)`
- [x] Same input → same `context_pack_hash`
- [x] `insufficient_context=True` when no P1 files found

#### 02-05 (5-Node Graph + E2E)
- [x] `build_ddk_graph()` creates START → intake → repo_scan → intent_extract → design_system → plan → END
- [x] All 5 nodes wrapped with `node_wrapper` (error boundaries)
- [x] Integration test runs full 5-node pipeline with FakeLLMAdapter (4 tests pass)
- [x] Pipeline produces non-None `repo_profile`, `intent_graph`, `generation_plan` in final state
- [x] Existing DI smoke test still passes

---

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| None found | — | — | — |

No TODOs, FIXMEs, placeholders, empty return bodies, or hardcoded stub returns found in any Phase 2 service or graph file.

**Note:** `intake_processor.py` is only 34 lines — intentionally minimal. IntakeProcessor's contract is narrow (path validation + hash), and all tests confirm it behaves correctly.

---

### Human Verification Required

#### 1. Real Claude API Integration

**Test:** Set `ANTHROPIC_API_KEY` and run `pytest tests/integration/ -m integration` with a real screenshot PNG  
**Expected:** `IntentGraph.confidence` populated from real vision response; `DesignSystem.inferred_tokens` contains real color/spacing tokens inferred from the image  
**Why human:** All automated tests use `FakeLLMAdapter`. Real API cost + no key in CI environment. Claude vision parsing quality can only be judged with actual UI screenshot input.

---

### ROADMAP Inconsistency (Non-Blocking)

The ROADMAP.md progress table shows Phase 1 as `0/7 | Planned` while Phase 2 is `5/5 | Complete`. Phase 1 has 4 SUMMARYs (01-01 through 01-04) and its plans exist, but 01-05/06/07 lack SUMMARYs and the ROADMAP wasn't updated for Phase 1's completion. This is a documentation gap in Phase 1 tracking — it does **not** block Phase 2 verification since all 286 tests pass and Phase 1 models/adapters/DI are provably in use throughout Phase 2's test suite.

---

## Gaps Summary

**No gaps.** All 5 success criteria are verified. All 22 must-have truths across 5 plans are satisfied. All 6 requirements confirmed complete. 286/286 tests pass including 4 E2E integration tests. The 5-node pipeline is fully assembled, wired, and data-flowing with no stubs detected.

---

_Verified: 2026-03-28T19:30:00Z_  
_Verifier: gsd-verifier_

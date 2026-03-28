---
phase: 02-ingestion-analysis
plan: 03
subsystem: services/llm-vision
tags: [llm, vision, intent-extraction, design-system, claude-sonnet, tdd]
dependency_graph:
  requires:
    - 02-01  # LLM adapters, Pydantic models, FakeLLMAdapter
  provides:
    - SemanticIntentExtractor.extract() → IntentGraph
    - DesignSystemInferencer.infer() → DesignSystem
    - DesignSystemInferencer.enrich_profile() → RepoProfile with tokens
    - intent_extract_node (LangGraph thin adapter)
    - design_system_node (LangGraph thin adapter)
  affects:
    - 02-04  # plan node — depends on intent_graph in state
    - 02-05  # builder.py partial graph assembly
tech_stack:
  added: []
  patterns:
    - FakeLLMAdapter key-based routing for unit test isolation
    - Message.images for vision inputs (base64 + media_type tuples)
    - complete_structured() for LLM structured JSON output
    - model_copy(update=...) for immutable Pydantic updates
    - Thin node pattern (D-05): node reads state → calls service → writes state
key_files:
  created:
    - src/ddk/services/semantic_intent_extractor.py
    - src/ddk/graph/nodes/intent_extract.py
    - tests/unit/services/test_semantic_intent_extractor.py
    - src/ddk/services/design_system_inferencer.py
    - src/ddk/graph/nodes/design_system.py
    - tests/unit/services/test_design_system_inferencer.py
  modified: []
decisions:
  - "D-05 enforced: nodes are thin adapters with zero business logic"
  - "D-06 enforced: all unit tests use FakeLLMAdapter with non-colliding keys ('you' vs 'analyze')"
  - "FakeLLMAdapter key='you' for SemanticIntentExtractor (system prompt: 'You are an expert UI analyst')"
  - "FakeLLMAdapter key='analyze' for DesignSystemInferencer (system prompt: 'Analyze UI screenshots...')"
  - "enrich_profile() uses model_copy(update=...) to avoid Pydantic mutation"
  - "typography tokens stored as {name: {value: str}} in DesignTokens.typography: dict[str,dict[str,str]]"
metrics:
  duration: 685s
  completed_date: "2026-03-28"
  tasks_completed: 2
  files_created: 6
  tests_added: 22
---

# Phase 02 Plan 03: SemanticIntentExtractor + DesignSystemInferencer Summary

**One-liner:** LLM vision pipeline services — claude-3-5-sonnet extracts IntentGraph from UI screenshots and infers DesignSystem tokens, both with FakeLLMAdapter unit tests and thin LangGraph node adapters.

## What Was Built

### Task 1: SemanticIntentExtractor (INGEST-04)

**`src/ddk/services/semantic_intent_extractor.py`**
- `SemanticIntentExtractor.extract(case_input: CaseInput) → IntentGraph`
- Reads first image from `case_input.image_paths[0]`, computes SHA256[:16] → `source_image_hash`
- Base64-encodes image bytes → `Message(images=[(b64, media_type)])`
- Sends to `claude-3-5-sonnet-20241022` via `complete_structured()` 
- Parses JSON response + injects `id=case_id` and `source_image_hash` before Pydantic validation
- System prompt from `docs/design/16-prompt-design.md §1` (starts with "You are an expert UI analyst")
- FakeLLMAdapter key: `"you"` (first word of system prompt, lowercase)

**`src/ddk/graph/nodes/intent_extract.py`**
- `intent_extract_node(state, **kwargs)` — thin adapter (D-05)
- Reads `state["case_input"]`, calls `SemanticIntentExtractor.extract()`, writes `intent_graph` + `current_node`

**Tests: 9 passing** (`tests/unit/services/test_semantic_intent_extractor.py`)
- `test_extract_returns_intent_graph` — correct type/fields
- `test_source_image_hash_computed` — SHA256[:16] matches
- `test_image_sent_as_base64` — base64 roundtrip + media type
- `test_system_prompt_starts_with_you` — key invariant
- `test_model_is_sonnet` — LLMCallConfig.model check
- `test_confidence_in_result` — confidence propagated
- `test_case_id_injected_as_graph_id` — id override
- `test_intent_extract_node_thin_adapter` — state in/out
- `test_intent_extract_node_no_llm_returns_error` — error boundary

---

### Task 2: DesignSystemInferencer (INGEST-05)

**`src/ddk/services/design_system_inferencer.py`**
- `DesignSystemInferencer.infer(case_input: CaseInput, repo_profile: RepoProfile) → DesignSystem`
- Sends all images from `case_input.image_paths` with repo framework/css context
- System prompt starts with "Analyze..." → FakeLLMAdapter key: `"analyze"` (no collision with `"you"`)
- Injects `case_id` into parsed response before Pydantic validation
- `DesignSystemInferencer.enrich_profile(design_system, repo_profile) → RepoProfile`
- Distributes `InferredDesignToken` objects by category into `DesignTokens` sub-fields
- Returns new `RepoProfile` via `model_copy(update=...)` — immutable, no mutation

**`src/ddk/graph/nodes/design_system.py`**
- `design_system_node(state, **kwargs)` — thin adapter (D-05)
- Reads `state["case_input"]` + `state["repo_profile"]`, calls inferencer, writes enriched `repo_profile`

**Tests: 13 passing** (`tests/unit/services/test_design_system_inferencer.py`)
- `test_infer_returns_design_system` — type + length check
- `test_infer_sets_case_id` — case_id override
- `test_enrich_profile_colors` — color tokens → design_tokens.colors
- `test_enrich_profile_spacing` — spacing tokens
- `test_enrich_profile_typography` — typography tokens
- `test_enrich_profile_border_radius` — border_radius tokens
- `test_enrich_profile_breakpoints` — breakpoint tokens
- `test_model_is_sonnet` — LLMCallConfig.model check
- `test_system_prompt_key_is_analyze` — key invariant
- `test_system_prompt_key_not_you` — no collision with Task 1
- `test_enrich_profile_does_not_mutate_original` — immutability check
- `test_design_system_node_enriches_profile` — node integration
- `test_design_system_node_no_llm_returns_error` — error boundary

---

## Test Results

```
uv run pytest tests/unit -x -q
226 passed in 0.24s
```

All 226 unit tests pass (22 new in this plan).

## Commits

| Hash | Description |
|------|-------------|
| `e06f5fb` | feat(02-03): implement SemanticIntentExtractor + intent_extract_node (INGEST-04) |
| `912f63a` | feat(02-03): implement DesignSystemInferencer + design_system_node (INGEST-05) |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

**Notable implementation notes:**
- `DesignTokens.typography` is `dict[str, dict[str, str]]` (not `dict[str, str]`), so typography tokens are stored as `{name: {"value": token.value}}` — consistent with the model spec
- Both nodes handle `context=None` gracefully, returning `terminal_state: "manual-review-required"` with error message containing "LLM"

## Known Stubs

None — both services are fully wired with real LLM adapter interface calls. FakeLLMAdapter is used only in tests.

## Self-Check: PASSED

# Phase 3 TDD Cycle — Code Generation & Normalization

## Summary

**Red → Green → Refactor** cycle executed for Phase 3 (GEN-01/GEN-02).

| Metric | Value |
|--------|-------|
| Baseline before RED | 350 tests passing |
| After RED (deletions) | 327 pass / 23 fail |
| After GREEN | 350 / 350 pass |
| Pyright errors (Phase 3 files) | 0 |
| Cycle duration | ~2 sessions |

---

## Files Involved

### Deleted (RED phase)
| File | Reason |
|------|--------|
| `src/ddk/services/code_generator.py` | Remove implementation before re-writing |
| `src/ddk/services/output_normalizer.py` | Remove implementation before re-writing |
| `src/ddk/graph/nodes/generate.py` | Remove thin adapter |
| `src/ddk/graph/nodes/normalize.py` | Remove thin adapter |

### Reverted (RED phase)
| File | Change |
|------|--------|
| `src/ddk/graph/builder.py` | 7-node → 5-node (removed generate/normalize imports, nodes, edges) |
| `tests/integration/test_ingestion_pipeline.py` | Removed Phase 3 fixtures; changed `current_node == "normalize"` to `"plan"` |

### Re-created (GREEN phase)
| File | Description |
|------|-------------|
| `src/ddk/services/code_generator.py` | CodeGenerator service — one LLM call per GenerationNode |
| `src/ddk/services/output_normalizer.py` | OutputNormalizer service — LLM-driven convention normalization |
| `src/ddk/graph/nodes/generate.py` | Thin adapter: LLM guard → CodeGenerator → state write |
| `src/ddk/graph/nodes/normalize.py` | Thin adapter: two guards → OutputNormalizer → state write |

### Restored (GREEN phase)
| File | Change |
|------|--------|
| `src/ddk/graph/builder.py` | Restored to 7-node pipeline with generate→normalize edges |
| `tests/integration/test_ingestion_pipeline.py` | Restored Phase 3 fixtures and `current_node == "normalize"` |

---

## RED Phase

### What was deleted
```
src/ddk/services/code_generator.py     # deleted
src/ddk/services/output_normalizer.py  # deleted
src/ddk/graph/nodes/generate.py        # deleted
src/ddk/graph/nodes/normalize.py       # deleted
```

### What was reverted
`builder.py` changed from 7-node to 5-node:
```python
# REMOVED:
from ddk.graph.nodes.generate import generate_node
from ddk.graph.nodes.normalize import normalize_node
workflow.add_node("generate", node_wrapper(generate_node))
workflow.add_node("normalize", node_wrapper(normalize_node))
workflow.add_edge("plan", "generate")
workflow.add_edge("generate", "normalize")
workflow.add_edge("normalize", END)
# REPLACED WITH:
workflow.add_edge("plan", END)
```

`test_ingestion_pipeline.py` reverted:
- Removed `_GENERATED_NODE_RESPONSE` and `_NORMALIZATION_RESPONSE` fixtures
- Removed `"generate"` and `"normalize"` keys from FakeLLMAdapter
- Changed assertion: `current_node == "normalize"` → `current_node == "plan"`

### Confirmed RED state
```
327 passed, 23 failed — ModuleNotFoundError for deleted modules
```

---

## GREEN Phase

### Key API discoveries during implementation

**LLM Adapter API** (NOT langchain):
```python
from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message, LLMResponse
# Message(role="system"|"user", content=str)
# LLMCallConfig(model, temperature, max_tokens)
# await adapter.complete(messages, config) -> LLMResponse
```

**FakeLLMAdapter key routing**:
- First system message content → `content.split()[0].lower()` = routing key
- CodeGenerator system prompt must start with `"Generate"` → key `"generate"`
- OutputNormalizer system prompt must start with `"Normalize"` → key `"normalize"`

**GeneratedArtifactSet.file_map type**:
- `file_map: dict[str, str]` — maps path to content string (NOT `GeneratedFile` objects)

**GenerationPlan.nodes type**:
- `nodes: list[GenerationNode]` — NOT a dict; build lookup with `{node.id: node for node in plan.nodes}`

### CodeGenerator (GEN-01)

```
src/ddk/services/code_generator.py
```

Contract:
- `CodeGenerator(llm: LLMAdapter)`
- `LLMCallConfig(model="claude-3-5-sonnet-20241022", temperature=0.0, max_tokens=4096)`
- `async def generate_all(plan, repo_profile, intent_graph, prompt) -> GeneratedArtifactSet`
- Empty plan → 0 LLM calls, returns empty `GeneratedArtifactSet`
- One LLM call per `GenerationNode` in `execution_order`
- `generation_trace` entries: `f"{node_id}:{node.target_path}"`
- `file_map` maps `path → content string`

Tests: `tests/unit/services/test_code_generator.py`
- `TestCodeGenerator` (7 tests) — service logic
- `TestGenerateNode` (2 tests) — thin adapter guards and delegation

### OutputNormalizer (GEN-02)

```
src/ddk/services/output_normalizer.py
```

Contract:
- `OutputNormalizer(llm: LLMAdapter)`
- `LLMCallConfig(model="claude-3-haiku-20240307", temperature=0.0, max_tokens=2048)`
- `async def normalize(artifacts, repo_profile) -> tuple[NormalizationReport, GeneratedArtifactSet]`
- **Identity short-circuit**: `artifacts.files == []` → return `(report, artifacts)` where `patched is artifacts` (same object)
- LLM response schema: `{"convention_fixes": [...], "unresolved_drift": [...], "patched_files": {}}`
- `drift_score_before = NormalizationReport.compute_drift_score(convention_fixes)`
- `drift_score_after` computed from `unresolved_drift` only (fixes not resolved)

Tests: `tests/unit/services/test_output_normalizer.py`
- `TestOutputNormalizer` (7 tests) — service logic
- `TestNormalizeNode` (2 tests) — thin adapter guards

### Graph nodes (thin adapters)

`generate.py`:
```python
# Guard: container.llm is None → terminal_state
# Otherwise: CodeGenerator.generate_all(...) → {"generated_artifacts": ..., "current_node": "generate"}
```

`normalize.py`:
```python
# Guard 1: container.llm is None → terminal_state
# Guard 2: state.get("generated_artifacts") is None → terminal_state
# Otherwise: OutputNormalizer.normalize(...) → {"normalization_report": ..., "generated_artifacts": ..., "current_node": "normalize"}
```

### Builder restored to 7-node

```
START → intake → repo_scan → intent_extract → design_system → plan → generate → normalize → END
```

### Integration test restored

`tests/integration/test_ingestion_pipeline.py`:
- Re-added `_GENERATED_NODE_RESPONSE` (empty artifact set JSON)
- Re-added `_NORMALIZATION_RESPONSE` (empty normalization JSON)
- Re-added `"generate"` and `"normalize"` keys to FakeLLMAdapter
- Restored `current_node == "normalize"` assertion

---

## REFACTOR Phase

### Pyright strict check (Phase 3 files)

```
0 errors, 0 warnings, 0 informations
```

**Fix applied**: `_NormalizationLLMOutput.convention_fixes` typed as `list[dict[str, Any]]` instead of `list[dict]` to satisfy pyright's strict unknown-member-type check.

### Docstrings
- All 4 new files have module-level docstrings explaining their role
- All public methods have docstrings with Args/Returns sections

---

## Test Results

```
350 passed in 1.05s
```

All 350 tests pass across:
- Unit tests: services (18), nodes (4), models, adapters
- Integration tests: full 7-node pipeline E2E (`test_ingestion_pipeline.py`, `test_generation_pipeline.py`)

---

## Lessons Learned

1. **Read the adapter API before implementing** — the project uses a custom `LLMAdapter` protocol with `Message`/`LLMCallConfig`, not langchain's `SystemMessage`/`HumanMessage`. Discovering this after an incorrect first draft cost one extra iteration.

2. **Identity semantics require no-copy** — the empty-artifacts short-circuit must return `artifacts` itself (`patched is artifacts`), not a copy. A `GeneratedArtifactSet(**artifacts.dict())` would create a new object and fail the identity assertion.

3. **`plan.nodes` is a list, not a dict** — `GenerationPlan.nodes: list[GenerationNode]` requires building an id→node lookup dict before use.

4. **FakeLLMAdapter routing by first word** — system prompts must begin with the correct word (`Generate`, `Normalize`, `Senior`, etc.) for the fake to route correctly. This is a test-doubles convention that must be respected in all service implementations.

5. **Thin adapters stay thin** — `generate.py` and `normalize.py` contain only guards + delegation. No business logic in nodes; all logic belongs in services.

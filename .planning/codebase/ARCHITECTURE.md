# Architecture

**Analysis Date:** 2024-12-19

## Pattern Overview

**Overall:** LangGraph-based AI-driven code generation pipeline with staged validation and self-healing

**Key Characteristics:**
- **10-node linear pipeline with conditional routing** — forward path (intake → repo_scan → intent_extract → design_system → plan → generate → normalize → validate) with conditional branching at validate node
- **Stateless node design** — all nodes are thin adapters; business logic lives in services layer
- **Immutable state propagation** — GraphState TypedDict passed through LangGraph with additive-only mutations
- **Dependency injection via ServiceContainer** — LangGraph context_schema injects adapters + services into every node
- **Error boundary wrapping** — all nodes wrapped with `node_wrapper` for graceful degradation
- **Self-healing validation loop** — validate → router → {pass/exhausted → certify, fix_available → autofix} with oscillation detection and retry budgeting

## Layers

### Models Layer

**Purpose:** Data structures and domain entities using Pydantic v2 validation

**Location:** `src/ddk/models/`

**Contains:** 24 model files covering:
- Input models: `CaseInput`, `RepoProfile`, `IntentGraph`
- Generation models: `GenerationPlan`, `GeneratedArtifactSet`, `GeneratedFile`, `NormalizationReport`
- Validation models: `RuntimeValidationReport`, `FailureRecord`, `VisualRegressionReport`, `FixAttempt`
- Certification models: `Scorecard`, `ReleaseDecision`, `EvidencePack`
- Configuration: `DdalggakConfig`, `ContextPack`, `ContextChunk`
- All inherit from `DDKBaseModel` (`_base.py`) which enforces frozen=False, validate_assignment=True, extra="forbid"

**Depends on:** Python stdlib, Pydantic

**Used by:** All layers (adapters, services, nodes reference these models)

### Adapter Layer (Port & Adapter Pattern)

**Purpose:** Abstract external I/O, business services, and runtime dependencies via Protocol interfaces

**Location:** `src/ddk/adapters/`

**Contains:** 7 adapter Protocols (instantiated concretely in runner):

1. **LLMAdapter** (`llm/base.py`)
   - Methods: `complete()`, `complete_structured()`
   - Concrete: `ClaudeAdapter` (`llm/claude.py`) wraps Anthropic SDK
   - Fakes: `FakeLLMAdapter` for testing

2. **FilesystemPort** (`filesystem.py`)
   - Methods: `read()`, `write()`, `exists()`, `list_files()`
   - Local filesystem abstraction
   - Isolates I/O for testability

3. **GitAdapter** (`git.py` interface, `local_git.py` concrete)
   - Methods: `clone()`, `commit()`, `create_worktree()`, `checkout_ref()`
   - Handles version control via git-python library
   - Enables rollback/checkpoint management in validation loop

4. **SandboxAdapter** (`sandbox/base.py`)
   - Methods: `create()`, `run_command()`, `cleanup()`
   - Implementations: `TempDirSandbox` for isolated execution
   - Includes execution policy enforcement (`sandbox/policy.py`)

5. **BuildRunner** (`build_runner.py`)
   - Methods: `build()`, `type_check()`, `lint()`, `test()`
   - Concrete: `SubprocessBuildRunner` runs npm/python build commands
   - Returns structured `CommandResult` with returncode, stdout, stderr

6. **PlaywrightAdapter** (`playwright_browser.py`)
   - Methods: `launch_browser()`, `navigate()`, `screenshot()`, `get_console_logs()`
   - Browser automation via Playwright
   - Null implementation: `NullPlaywrightAdapter` for headless/CI environments

7. **ScreenshotDiffAdapter** (`screenshot_diff.py`)
   - Methods: `compute_diff()`, `compare()`
   - Visual regression detection via SSIM
   - Concrete: `ScreenshotDiffLocal` uses scipy/numpy

**Depends on:** External SDKs (anthropic, playwright, gitpython), Python stdlib

**Used by:** Services access adapters through ServiceContainer; nodes never directly call adapters

### Services Layer (Business Logic)

**Purpose:** Pure business logic orchestrators that compose adapters and models; stateless, testable

**Location:** `src/ddk/services/`

**Contains:** 16 service classes (one per business capability):

**Phase 2 & 3 services (forward path):**
- `IntakeProcessor` — validates CaseInput, computes image hashes
- `RepoConventionScanner` — analyzes target repo (npm/TypeScript/React conventions) → RepoProfile
- `SemanticIntentExtractor` — LLM-based: design images + prompt → IntentGraph
- `DesignSystemInferencer` — LLM-based: design system inference (colors, tokens, spacing)
- `GenerationPlanner` — LLM-based: creates ordered GenerationPlan with task graph
- `ContextPackBuilder` — deterministic (MAX_FILES=6, MAX_LINES=300, P1-P5 priority) → ContextPack
- `CodeGenerator` — LLM-based: GenerationPlan → GeneratedArtifactSet
- `OutputNormalizer` — post-processes generated code against RepoProfile conventions

**Phase 4 services (validation & self-healing):**
- `RuntimeValidator` — orchestrates sandbox validation (build, type-check, lint, runtime tests, visual regression)
- `FailureClassifier` — categorizes failures into taxonomy (FT-BUILD-*, FT-TYPE-*, etc.)
- `AutoFixPlanner` — selects repair rule (9 rule types) and applies patches
- `RollbackController` — manages git worktree checkpoints and rollback on failure

**Phase 5 services (certification):**
- `ScorecardCalculator` — computes precision/maintainability/automation/scalability scores
- `ReleaseGate` — generates ReleaseDecision (ready/blocked/manual-review) from scorecard + failures
- `EvidencePackBuilder` — bundles all execution artifacts, logs, reports into EvidencePack
- `CaseArtifactStore` — persists case outputs to disk

**Depends on:** Models layer (input/output), Adapter layer (via DI), external LLM APIs

**Used by:** Graph nodes instantiate services and call their orchestration methods

### Graph Layer (LangGraph Orchestration)

**Purpose:** Define stateful computation graph topology and node/edge connections

**Location:** `src/ddk/graph/`

**Contains:**

1. **GraphState** (`state.py`)
   - TypedDict with 19 fields covering entire pipeline state
   - Tracks case_input, repo_profile, intent_graph, generation_plan, generated_artifacts, reports, decision, budget, error tracking
   - Immutable-by-convention (all reads, no mutations)
   - `initial_state(case_input)` factory returns complete initial state

2. **ServiceContainer** (`context.py`)
   - Dataclass holding 7 adapters + 10 services (optional until instantiated)
   - Injected into graph via StateGraph(GraphState, context_schema=ServiceContainer)
   - Nodes access via `kwargs.get("context")`

3. **Nodes** (`nodes/`)
   - 10 async node functions, each wrapped with `node_wrapper`
   - **Thin adapter pattern:** node reads state, calls service, returns partial state dict

   **Node sequence:**
   ```
   START → intake → repo_scan → intent_extract → design_system → plan
        → generate → normalize → validate → [route_after_validate]
        → {pass|exhausted → certify, fix_available → autofix}
        → certify → END
   ```

   - `intake_node` — validates CaseInput
   - `repo_scan_node` — analyzes repo conventions → RepoProfile
   - `intent_extract_node` — LLM: design → IntentGraph
   - `design_system_node` — LLM: design system tokens → DesignSystem
   - `plan_node` — LLM: plan generation tasks → GenerationPlan
   - `generate_node` — LLM: execute tasks → GeneratedArtifactSet
   - `normalize_node` — post-process artifacts → NormalizationReport
   - `validate_node` — sandbox checks + visual regression → RuntimeValidationReport
   - `autofix_node` — selects repair rule, patches code, tracks retry budget + oscillation
   - `certify_node` — calculates scorecard, release decision, evidence pack → terminal_state

4. **Router** (`router.py`)
   - `route_after_validate(state)` → Literal["pass", "fix_available", "exhausted"]
   - Determines routing based on:
     - All checks pass? → "pass"
     - Budget exhausted or oscillation detected? → "exhausted"
     - Failures exist & budget > 0 & no oscillation? → "fix_available"

5. **Builder** (`builder.py`)
   - `build_ddk_graph() → StateGraph`
   - Constructs 10-node linear graph with:
     - Linear edges: START → intake → … → normalize → validate
     - Conditional edge: validate → router → {pass/exhausted → certify, fix_available → autofix}
     - Back-edge: autofix → validate (self-healing loop)
     - Final: certify → END

6. **Node Wrapper** (`nodes/_wrapper.py`)
   - Error boundary: catches OS/PermissionError/TimeoutError/generic Exception
   - Extracts ServiceContainer from LangGraph runtime config and injects as `context` kwarg
   - Returns safe terminal state on error

### DI & Runtime

**Purpose:** Instantiate and inject dependencies at runtime

**Location:** `src/ddk/services/pipeline_runner.py`

**Contains:**
- `RuntimeServices` dataclass — holds 7 concrete adapters
- `PipelineRunner.run_case(case_input)` — orchestrates:
  1. Instantiate concrete services (RollbackController, RuntimeValidator, FailureClassifier)
  2. Create ServiceContainer with adapters + services
  3. Import and build graph via `build_ddk_graph()`
  4. Invoke compiled graph via `ainvoke(initial_state, context=container)`
  5. Return final GraphState dict

## Data Flow

### Forward Path (Ingestion → Certification)

```
START
  ↓
intake: CaseInput validated
  ↓
repo_scan: Analyze repo conventions → RepoProfile
  ↓
intent_extract: LLM(design_images + prompt) → IntentGraph
  ↓
design_system: LLM(intent_graph) → DesignSystem tokens
  ↓
plan: LLM(intent + design_system) → GenerationPlan (ordered tasks)
  ↓
generate: LLM(for each task in GenerationPlan) → GeneratedArtifactSet
  ↓
normalize: Post-process(artifacts, repo_conventions) → NormalizationReport, patched_artifacts
  ↓
validate: Sandbox(build, type-check, lint, runtime-test) + Visual regression → RuntimeValidationReport + VisualRegressionReport
  ↓
route_after_validate
  ├─ "pass" (all checks pass) → certify
  ├─ "exhausted" (budget=0 or oscillation) → certify
  └─ "fix_available" (failures exist & budget>0 & no oscillation)
       ↓
       autofix: AutoFixPlanner selects repair rule → patches → decrements budget → appends failure_hash
            ↓
            → validate (back-edge loop)
  ↓
certify: Scorecard + ReleaseDecision + EvidencePack
  ↓
END (terminal_state = decision)
```

### State Management

**Immutability pattern:** Every node returns `dict[str, Any]` with only *new* or *modified* fields. LangGraph merges returned dict into GraphState.

**Key state progression:**
1. `initial_state()` creates complete GraphState with all None/[] defaults
2. intake_node adds validated `case_input`
3. repo_scan_node adds `repo_profile`
4. intent_extract_node adds `intent_graph`
5. ... accumulates through pipeline
6. validate_node adds `runtime_validation_report`, optionally `visual_regression_report`
7. autofix_node appends to `fix_attempts`, decrements `retry_budget_remaining`, appends to `failure_hash_history`
8. autofix_node → validate loop maintains state, router always reads latest state
9. certify_node computes `scorecard`, `release_decision`, `evidence_pack` and sets `terminal_state`

**Oscillation detection (Phase 4):**
- autofix_node computes hash = `frozenset((f.taxonomy_id, f.file_path) for f in failures)`
- Appends hash to `failure_hash_history` BEFORE applying fix
- route_after_validate checks if current_hash in seen history
- If yes, returns "exhausted" (same failures recurring)
- Critical: uses (taxonomy_id, file_path), NOT failure.id (UUID regenerated each run)

**Budget tracking:**
- GraphState.retry_budget_remaining initialized to 3
- autofix_node decrements by 1 after each attempt
- route_after_validate returns "exhausted" when budget ≤ 0

## Key Abstractions

### LangGraph StateGraph & GraphState

**Purpose:** Stateful computation orchestration across 10 nodes

**Examples:** 
- `src/ddk/graph/state.py`: GraphState TypedDict definition
- `src/ddk/graph/builder.py`: StateGraph construction

**Pattern:**
```python
workflow = StateGraph(GraphState, context_schema=ServiceContainer)
workflow.add_node("node_name", node_wrapper(node_fn))
workflow.add_edge("node_a", "node_b")  # linear
workflow.add_conditional_edges("validate", route_after_validate, {...})  # branching
compiled = workflow.compile()
result = await compiled.ainvoke(initial_state(input), context=container)
```

### Port & Adapter (Protocol-based)

**Purpose:** Decouple business logic from external I/O

**Examples:**
- LLMAdapter (`src/ddk/adapters/llm/base.py`) protocol
- ClaudeAdapter (`src/ddk/adapters/llm/claude.py`) concrete implementation
- FakeLLMAdapter (in tests) for testing

**Pattern:** Services take adapters as constructor params (DI). At runtime, concrete adapters injected via ServiceContainer. Tests inject fake adapters.

### Thin Adapter Nodes

**Purpose:** Nodes don't contain logic; they delegate to services

**Examples:**
- `intake_node` calls `IntakeProcessor()`
- `generate_node` calls `CodeGenerator()`
- `validate_node` calls `RuntimeValidator()`

**Pattern:**
```python
async def node_name(state: dict, **kwargs) -> dict:
    service = ServiceClass(...)
    result = await service.method(state[...])
    return {"field": result, "current_node": "name"}
```

### Service Composition

**Purpose:** Business logic orchestrates multiple adapters

**Examples:**
- `RuntimeValidator` composes: SandboxAdapter + BuildRunner + PlaywrightAdapter + ScreenshotDiffAdapter
- `FailureClassifier` receives failures, categorizes by taxonomy
- `AutoFixPlanner` receives classified failures, selects repair rule

**Pattern:** Services are stateless, take models as input, return models as output.

## Entry Points

### CLI Entry Point

**Location:** `src/ddk/cli/` (package, also started by `python -m ddk` through `src/ddk/__main__.py`)

**Triggers:**
- `ddk run <image>` — run the full 10-node graph on a design image; `status`, `certify`, `report`,
  `apply`, `rollback` read or act on the saved case
- `ddk demo` — the same loop with a recorded model reply and no API key
- `ddk doctor` / `ddk preflight` — check the environment (`doctor --install-browser` downloads Chromium)
- `ddk design new <IDEA>` — run design studio (separate from delivery pipeline)
- `ddk proof`, `ddk audit`, `ddk init`, `ddk serve`, `ddk install`, `ddk version`

**Responsibilities:**
1. Parse CLI args (`cli/app.py`, one module per command group)
2. Load DdalggakConfig from env (`cli/common.py`)
3. Instantiate concrete adapters (ClaudeAdapter, TempDirSandbox, ChromiumBrowserAdapter, LocalGit, etc.) in `cli/runtime.py`
4. Create RuntimeServices and PipelineRunner
5. Invoke PipelineRunner.run_case(case_input)
6. Return result or error; user-facing text goes through `ddk.i18n.t()`

### Server Entry Point

**Location:** `src/ddk/server.py`

**Triggers:** MCP (Model Context Protocol) server for Design Studio only

**Responsibilities:**
- Provides `design_new()` tool for Claude MCP clients
- Separate from delivery pipeline (no validation/self-healing)

## Error Handling

**Strategy:** Catch errors at boundary (node_wrapper), fail gracefully to manual-review-required state

**Patterns:**

1. **OS/Permission/Timeout errors** → node_wrapper catches, returns:
   ```python
   {
       "terminal_state": "manual-review-required",
       "error_message": f"OS/timeout error in node: {exc}",
   }
   ```

2. **Missing adapters/services** → nodes check `container is None` or `container.service is None`:
   ```python
   if container is None or container.runtime_validator is None:
       return {
           "terminal_state": "manual-review-required",
           "error_message": "RuntimeValidator not configured",
       }
   ```

3. **Business logic failures** → classified into failure taxonomy (FT-BUILD-*, FT-TYPE-*, etc.), tracked in RuntimeValidationReport, trigger autofix loop

4. **LLM errors** → adapters return LLMResponse with error field; services propagate; caught by node_wrapper

5. **Budget exhaustion or oscillation** → route_after_validate returns "exhausted", triggers certify with manual-review terminal state

## Cross-Cutting Concerns

**Logging:** 
- Structured logging via structlog (`src/ddk/logging/`)
- Secret redaction via security.redact (`src/ddk/security/redact.py`)
- JSON output for machine parsing

**Validation:**
- Pydantic v2 models enforce type safety on all data structures
- Field validators on input models (CaseInput requires 1-5 images, prompt 1-2000 chars)
- Failure taxonomy validation (FAILURE_TAXONOMY dict defines allowed codes)

**Authentication:**
- LLM API key via env var (DDK_ANTHROPIC_API_KEY)
- Git SSH key for repo operations (handled by local_git.py)
- No auth for sandbox/browser (local-only operations)

**Cost Tracking:**
- LLMResponse includes cost_usd, input_tokens, output_tokens
- GraphState.llm_call_records accumulates call metadata
- GraphState.total_cost_usd sums costs
- EvidencePack includes cost summary

**Reproducibility:**
- GraphState.reproducibility_seed optional seed for deterministic LLM
- ContextPackBuilder produces deterministic file selection via stable sort
- Node inputs always logged for replay

---

*Architecture analysis: 2024-12-19*

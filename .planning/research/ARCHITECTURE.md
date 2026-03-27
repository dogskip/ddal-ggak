# Architecture Research

**Domain:** LangGraph Pipeline — Design-to-Code Delivery Engine (Python 3.12+)
**Researched:** 2025-07-13
**Confidence:** HIGH

## System Overview

```
┌───────────────────────────────────────────────────────────────────────┐
│  Level 0 — Entry Layer (CLI / MCP)                                    │
│  ┌─────────┐  ┌─────────────┐                                         │
│  │ Typer   │  │ FastMCP     │  → both call build_ddk_graph()          │
│  │ CLI     │  │ Server      │                                         │
│  └────┬────┘  └──────┬──────┘                                         │
│       └──────┬───────┘                                                │
├──────────────┼────────────────────────────────────────────────────────┤
│  Level 1 — Orchestration (LangGraph StateGraph)                       │
│       ┌──────▼──────┐                                                 │
│       │  builder.py │ → compile() with context_schema=ServiceContainer│
│       └──────┬──────┘                                                 │
│  ┌───────────┼─────────────────────────────────────────────────┐      │
│  │  10 nodes │ ingest→repo_scan→intent→plan→generate→normalize │      │
│  │           │ →runtime_validate→visual_regress→auto_fix→certify│     │
│  └───────────┼─────────────────────────────────────────────────┘      │
│              │ each node: (state: GraphState, runtime: Runtime) → dict│
├──────────────┼────────────────────────────────────────────────────────┤
│  Level 2 — Domain Services (15 services)                              │
│  ┌───────────▼──────────────────────────────────────────────────┐     │
│  │ RepoScanner │ IntentExtractor │ CodeGenerator │ Normalizer   │     │
│  │ AutoFixPlanner │ RetryController │ ContextPackBuilder │ ...  │     │
│  └──────────────────────────┬──────────────────────────────────┘     │
├─────────────────────────────┼─────────────────────────────────────────┤
│  Level 3 — Adapters (Protocol-based)                                  │
│  ┌──────────────────────────▼──────────────────────────────────┐     │
│  │ LLMAdapter │ FilesystemAdapter │ GitAdapter │ SandboxAdapter │     │
│  │ PlaywrightAdapter │ ScreenshotDiffAdapter │ BuildRunner     │     │
│  └─────────────────────────────────────────────────────────────┘     │
├───────────────────────────────────────────────────────────────────────┤
│  Level 4 — Evidence & Persistence                                     │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ .ddk/cases/C-xxx/ → JSON artifacts, screenshots, logs        │     │
│  └──────────────────────────────────────────────────────────────┘     │
└───────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `cli.py` | Parse user input, create `CaseInput`, invoke graph | `builder.py`, `WorkspaceManager` |
| `builder.py` | Assemble `StateGraph`, register nodes/edges, compile | All node functions, `edges.py` |
| `state.py` | Define `GraphState` TypedDict, `initial_state()` | Every node (read/write) |
| `ServiceContainer` | **NEW**: Hold adapter + service instances for DI | `builder.py` (via `context_schema`), all nodes (via `runtime`) |
| `nodes/*.py` | Thin orchestration: read state → call service → return delta | Services, `ServiceContainer` |
| `services/*.py` | Domain logic: single-responsibility business rules | Adapters (via Protocol injection) |
| `adapters/*.py` | External system abstraction: LLM, git, filesystem, browser | External systems only |
| `models/*.py` | Pydantic v2 data contracts, validation | Consumed by all layers |
| `workspace/` | `.ddk/` directory management, checkpoints, rollback | `FilesystemAdapter`, `GitAdapter` |

## Critical Architecture Decision: Dependency Injection via `context_schema`

**Confidence:** HIGH — Verified against LangGraph v1.1.3 live API.

### The Problem in the Existing Design

The design docs (doc 19) show nodes instantiating services directly:

```python
# CURRENT DESIGN — services created inside nodes (problematic)
async def repo_scan_node(state: GraphState) -> dict:
    scanner = RepoConventionScanner()  # ← hard-coupled, untestable
    profile = await scanner.scan(state["case_input"].repo_path)
    return {"repo_profile": profile, "current_node": "repo_scan"}
```

This creates **hard coupling** between nodes and service implementations. Testing a node requires mocking module-level imports. The `.from_config()` factory methods are slightly better but still couple nodes to environment config at instantiation time.

### The Solution: LangGraph `context_schema` + `Runtime`

LangGraph v1.1.3 provides first-class dependency injection via `context_schema`. This was introduced in v0.6.0 (replacing the deprecated `config_schema`).

**How it works:**
1. Define a `context_schema` dataclass that holds all injectable dependencies
2. Pass it to `StateGraph(state_schema, context_schema=MyContext)`
3. Nodes declare `runtime: Runtime[MyContext]` parameter — LangGraph auto-injects it
4. At invocation time, pass `context=MyContext(...)` to `graph.invoke()`

**Verified working pattern:**

```python
# src/ddk/graph/context.py — NEW FILE
from __future__ import annotations
from dataclasses import dataclass, field
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.git import GitAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter
from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.llm.recorder import LLMCallRecorder
from ddk.adapters.llm.router import ModelRouter
from ddk.adapters.llm.cost_tracker import CostTracker
from ddk.workspace.manager import WorkspaceManager


@dataclass
class ServiceContainer:
    """Run-scoped dependency container injected into every LangGraph node.
    
    Created once per graph invocation. Adapters are Protocol-based,
    allowing test doubles without patching.
    """
    # Core adapters
    llm: LLMAdapter
    filesystem: FilesystemAdapter
    git: GitAdapter
    sandbox: SandboxAdapter
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter
    build_runner: BuildRunner
    
    # Cross-cutting concerns
    recorder: LLMCallRecorder
    model_router: ModelRouter
    cost_tracker: CostTracker
    workspace: WorkspaceManager
```

```python
# src/ddk/graph/builder.py — UPDATED
from langgraph.graph import StateGraph, END
from .state import GraphState
from .context import ServiceContainer

def build_ddk_graph() -> "CompiledGraph":
    workflow = StateGraph(GraphState, context_schema=ServiceContainer)
    # ... register nodes and edges ...
    return workflow.compile()
```

```python
# src/ddk/graph/nodes/repo_scan.py — UPDATED
from langgraph.runtime import Runtime
from ddk.graph.state import GraphState
from ddk.graph.context import ServiceContainer
from ddk.services.repo_scanner import RepoConventionScanner

async def repo_scan_node(state: GraphState, runtime: Runtime[ServiceContainer]) -> dict:
    scanner = RepoConventionScanner(filesystem=runtime.context.filesystem)
    profile = await scanner.scan(state["case_input"].repo_path)
    return {"repo_profile": profile, "current_node": "repo_scan"}
```

```python
# Invocation (from CLI or MCP)
container = ServiceContainer(
    llm=AnthropicAdapter(api_key=key, default_model=model),
    filesystem=FilesystemAdapter(),
    git=GitAdapter(),
    # ... all other adapters
)
graph = build_ddk_graph()
result = await graph.ainvoke(
    initial_state(case_input),
    context=container,
)
```

### Why This Over Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| **`context_schema` (recommended)** | First-class LangGraph API; auto-injected; type-safe; propagates to subgraphs | Requires LangGraph ≥0.6.0 | ✅ Use this |
| Service creation inside nodes | Simple; matches design docs | Untestable; hard-coupled; env-dependent | ❌ Avoid |
| Module-level singletons | Zero config | Global state; test pollution; import-time side effects | ❌ Avoid |
| Pass services in GraphState | Works anywhere | State pollution; services aren't state; serialization issues | ❌ Avoid |
| `RunnableConfig` configurable | Pre-0.6 approach | Deprecated; string-keyed dict; no type safety | ❌ Deprecated |

## Recommended Project Structure

The design doc `13-project-structure.md` layout is sound. One addition needed:

```
src/ddk/
├── __init__.py
├── cli.py                      # Typer app + subcommands
├── mcp_server.py               # FastMCP server
│
├── models/                     # Pydantic v2 contracts (pure data)
│   ├── __init__.py
│   ├── _base.py                # DDKBaseModel with shared config
│   ├── input.py                # CaseInput
│   ├── repo.py                 # RepoProfile, NamingRules, etc.
│   ├── intent.py               # IntentGraph, LayoutRegion, etc.
│   ├── generation.py           # GenerationPlan, GeneratedFile
│   ├── normalization.py        # NormalizationReport
│   ├── validation.py           # RuntimeValidationReport, FailureRecord
│   ├── visual.py               # VisualRegressionReport
│   ├── fix.py                  # FixAttempt
│   ├── scorecard.py            # Scorecard
│   ├── release.py              # ReleaseDecision
│   ├── llm.py                  # LLMCallRecord
│   └── evidence.py             # EvidencePack
│
├── graph/                      # LangGraph orchestration
│   ├── __init__.py
│   ├── state.py                # GraphState TypedDict + initial_state()
│   ├── context.py              # ★ NEW: ServiceContainer dataclass
│   ├── builder.py              # build_ddk_graph() with context_schema
│   ├── edges.py                # Conditional routing functions
│   └── nodes/                  # Thin node functions
│       ├── __init__.py
│       ├── _wrapper.py         # ★ NEW: _node_wrapper with Runtime injection
│       ├── ingest.py
│       ├── repo_scan.py
│       ├── intent_extract.py
│       ├── plan.py
│       ├── generate.py
│       ├── normalize.py
│       ├── runtime_validate.py
│       ├── visual_regress.py
│       ├── auto_fix.py
│       └── certify.py
│
├── services/                   # Domain logic (business rules)
│   ├── __init__.py
│   ├── repo_scanner.py
│   ├── intent_extractor.py
│   ├── design_inferencer.py
│   ├── generation_planner.py
│   ├── code_generator.py
│   ├── normalizer.py
│   ├── runtime_validator.py
│   ├── visual_regression.py
│   ├── failure_classifier.py
│   ├── auto_fix_planner.py
│   ├── retry_controller.py
│   ├── context_pack_builder.py
│   ├── benchmark_service.py
│   ├── release_decision.py
│   └── evidence_builder.py
│
├── adapters/                   # External system interfaces
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py             # LLMAdapter Protocol
│   │   ├── anthropic.py        # AnthropicAdapter
│   │   ├── openai.py           # OpenAIAdapter
│   │   ├── fake.py             # ★ NEW: FakeLLM for testing
│   │   ├── recorder.py         # LLMCallRecorder (decorator/wrapper)
│   │   ├── router.py           # ModelRouter
│   │   └── cost_tracker.py     # CostTracker
│   ├── filesystem.py           # FilesystemAdapter Protocol + impl
│   ├── git.py                  # GitAdapter Protocol + impl
│   ├── sandbox/
│   │   ├── __init__.py
│   │   ├── base.py             # SandboxAdapter Protocol
│   │   ├── worktree.py         # WorktreeSandbox
│   │   └── policy.py           # CommandAllowlist, PathPolicy
│   ├── build_runner.py         # BuildRunner Protocol + impl
│   ├── playwright_browser.py   # PlaywrightAdapter Protocol + impl
│   ├── screenshot_diff.py      # ScreenshotDiffAdapter (SSIM)
│   └── console_capture.py      # ConsoleCapture
│
├── workspace/                  # .ddk/ directory management
│   ├── __init__.py
│   ├── manager.py
│   ├── checkpoint.py
│   └── rollback.py
│
└── preflight/                  # Environment checks
    ├── __init__.py
    └── doctor.py
```

### Structure Rationale

- **`graph/context.py` (NEW):** Single source of truth for the DI container. Every node knows exactly what dependencies are available. Separating from `state.py` keeps state (data flow) and context (dependency injection) concerns distinct.
- **`graph/nodes/_wrapper.py` (NEW):** Centralizes error handling wrapper. Must accept `Runtime[ServiceContainer]` and forward it to wrapped node functions.
- **`adapters/llm/fake.py` (NEW):** Test double is a first-class citizen, not an afterthought. Used in all tests and E2E.
- **`models/` stays pure:** No imports from services, adapters, or graph. This is the foundation layer — everything depends on it, it depends on nothing.

### Import Dependency Rules (Enforced)

```
models/  ← depends on nothing (Pydantic only)
   ↑
adapters/ ← depends on models/ (types for input/output)
   ↑
services/ ← depends on models/ + adapters/ (via Protocol injection)
   ↑
graph/   ← depends on models/ + services/ + adapters/ (via ServiceContainer)
   ↑
cli.py   ← depends on graph/ + workspace/ (assembles everything)
```

**Violations to watch for:**
- Services importing from `graph/` → circular dependency
- Adapters importing from `services/` → inverted dependency
- Nodes doing domain logic directly → should call service instead

## Architectural Patterns

### Pattern 1: Protocol-Based Adapter Abstraction

**What:** Every external system interaction is defined by a `typing.Protocol`, not a concrete class. Services depend on Protocols; concrete implementations are injected via `ServiceContainer`.

**When to use:** All adapters (LLM, filesystem, git, sandbox, browser, screenshot diff).

**Trade-offs:**
- ✅ Swap real for fake in tests with zero monkey-patching
- ✅ Pyright catches mismatches at type-check time
- ✅ Multiple implementations (e.g., Anthropic vs OpenAI) share same interface
- ⚠️ Slightly more boilerplate than just importing a class

**Example:**

```python
# src/ddk/adapters/llm/base.py
from typing import Protocol

class LLMAdapter(Protocol):
    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse: ...
    async def complete_structured(self, messages: list[Message], config: LLMCallConfig, output_schema: type) -> LLMResponse: ...

# src/ddk/adapters/llm/fake.py
class FakeLLM:
    """Test double — returns canned responses keyed by node name."""
    def __init__(self, responses: dict[str, str] | None = None):
        self._responses = responses or {}
        self.calls: list[tuple[list[Message], LLMCallConfig]] = []
    
    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse:
        self.calls.append((messages, config))
        content = self._responses.get(config.model, '{"result": "fake"}')
        return LLMResponse(content=content, model=config.model, provider="fake",
                           input_tokens=10, output_tokens=10, cost_usd=0.0, raw={})
    
    async def complete_structured(self, messages, config, output_schema):
        return await self.complete(messages, config)

# src/ddk/adapters/filesystem.py
from typing import Protocol
from pathlib import Path

class FilesystemPort(Protocol):
    def read_text(self, path: Path) -> str: ...
    def write_text(self, path: Path, content: str) -> None: ...
    def list_dir(self, path: Path) -> list[Path]: ...
    def exists(self, path: Path) -> bool: ...

class FilesystemAdapter:
    """Real implementation."""
    def read_text(self, path: Path) -> str:
        return path.read_text()
    # ... etc

class InMemoryFilesystem:
    """Test double — stores files in dict."""
    def __init__(self):
        self._files: dict[str, str] = {}
    # ... etc
```

### Pattern 2: Thin Node, Fat Service

**What:** LangGraph node functions are thin orchestration wrappers (5-15 lines). All domain logic lives in services. A node's job: read state → get service from runtime → call service → return state delta.

**When to use:** Every node. No exceptions.

**Trade-offs:**
- ✅ Nodes are trivially testable (mock service, assert call)
- ✅ Services are testable in isolation (no LangGraph dependency)
- ✅ Services are reusable outside graph context
- ⚠️ Extra indirection vs doing logic in the node

**Example:**

```python
# src/ddk/graph/nodes/intent_extract.py
from langgraph.runtime import Runtime
from ddk.graph.state import GraphState
from ddk.graph.context import ServiceContainer
from ddk.services.intent_extractor import SemanticIntentExtractor

async def intent_extract_node(state: GraphState, runtime: Runtime[ServiceContainer]) -> dict:
    """Thin node: delegates to SemanticIntentExtractor service."""
    extractor = SemanticIntentExtractor(
        llm=runtime.context.llm,
        model_router=runtime.context.model_router,
        recorder=runtime.context.recorder,
    )
    graph, record = await extractor.extract(
        image_paths=state["case_input"].image_paths,
        prompt=state["case_input"].prompt,
        reference_notes=state["case_input"].reference_notes,
    )
    return {
        "intent_graph": graph,
        "llm_call_records": state["llm_call_records"] + [record.call_id],
        "total_cost_usd": state["total_cost_usd"] + (record.cost_usd or 0.0),
        "current_node": "intent_extract",
    }
```

### Pattern 3: Error Boundary Wrapper with Runtime Forwarding

**What:** All nodes are wrapped in `_node_wrapper` that catches OS/validation/timeout errors and converts them to terminal states. The wrapper must forward `runtime` to the inner function.

**When to use:** Every node registration in `builder.py`.

**Verified:** `functools.partial(_node_wrapper, actual_node)` correctly preserves LangGraph's `runtime` parameter injection.

```python
# src/ddk/graph/nodes/_wrapper.py
from __future__ import annotations
import asyncio
import functools
from typing import Callable, Awaitable
from pydantic import ValidationError
from langgraph.runtime import Runtime
from ddk.graph.state import GraphState
from ddk.graph.context import ServiceContainer

async def _node_wrapper(
    node_fn: Callable[..., Awaitable[dict]],
    state: GraphState,
    runtime: Runtime[ServiceContainer],
) -> dict:
    """Error boundary for all LangGraph nodes.
    
    Catches non-LLM exceptions and converts to terminal states.
    LLM errors propagate — handled by safe_llm_call in adapters.
    """
    try:
        return await node_fn(state, runtime)
    except (OSError, PermissionError, FileNotFoundError) as e:
        return {
            "terminal_state": "manual-review-required",
            "error_message": f"[{node_fn.__name__}] {type(e).__name__}: {e}",
            "current_node": node_fn.__name__,
        }
    except ValidationError as e:
        return {
            "terminal_state": "manual-review-required",
            "error_message": f"[{node_fn.__name__}] Schema validation: {e.error_count()} errors",
            "current_node": node_fn.__name__,
        }
    except asyncio.TimeoutError:
        return {
            "terminal_state": "runtime-failed",
            "error_message": f"[{node_fn.__name__}] Timeout exceeded",
            "current_node": node_fn.__name__,
        }
    except Exception as e:
        return {
            "terminal_state": "manual-review-required",
            "error_message": f"[{node_fn.__name__}] Unexpected: {type(e).__name__}: {e}",
            "current_node": node_fn.__name__,
        }

# Usage in builder.py:
# workflow.add_node("repo_scan", functools.partial(_node_wrapper, repo_scan_node))
```

### Pattern 4: Service Constructor Injection (Not Factory Methods)

**What:** Services receive their adapter dependencies through `__init__`, not through class methods like `.from_config()`. The `ServiceContainer` does the wiring.

**Why:** The design docs use `.from_config()` factory methods which read env vars at service creation time. This couples services to the environment. Constructor injection keeps services pure.

```python
# INSTEAD OF (design doc pattern):
class SemanticIntentExtractor:
    @classmethod
    def from_config(cls): ...  # reads env vars

# USE:
class SemanticIntentExtractor:
    def __init__(self, llm: LLMAdapter, model_router: ModelRouter, recorder: LLMCallRecorder):
        self._llm = llm
        self._router = model_router
        self._recorder = recorder
    
    async def extract(self, image_paths, prompt, reference_notes):
        config = self._router.config_for("intent_extract")
        response = await self._llm.complete_structured(
            messages=self._build_messages(image_paths, prompt, reference_notes),
            config=config,
            output_schema=IntentGraph,
        )
        record = self._recorder.record(stage="intent_extract", response=response, config=config)
        return IntentGraph.model_validate_json(response.content), record
```

## Async/Sync Boundary

**Confidence:** HIGH — Verified against LangGraph v1.1.3.

### Rule: All nodes are `async def`

LangGraph supports mixing sync and async nodes in the same graph. However, for consistency and because many operations in ddalggak are I/O-bound (LLM calls, subprocess, file I/O, Playwright), **all node functions should be `async def`**.

### Where sync is fine

Sync code is fine *inside* services that don't do I/O:
- `RetryBudgetController.is_non_improving()` — pure logic
- `FailureClassifier.classify()` — pure logic
- `BenchmarkScorecardService.compute()` — pure computation
- `ReleaseDecisionService.decide()` — pure rule aggregation

These services can have sync methods. The node function that calls them is still `async def`.

### Where async is required

- LLM calls (always async via httpx/anthropic/openai SDKs)
- Playwright browser automation
- Subprocess execution (build, typecheck, lint)
- File I/O in hot paths (use `asyncio.to_thread` for heavy reads)
- Git operations (use `asyncio.to_thread` wrapping GitPython)

### GitPython caveat

GitPython is synchronous. Wrap with `asyncio.to_thread`:

```python
class GitAdapter:
    async def create_worktree(self, path: Path, branch: str) -> Path:
        return await asyncio.to_thread(self._sync_create_worktree, path, branch)
    
    def _sync_create_worktree(self, path: Path, branch: str) -> Path:
        repo = git.Repo(path)
        # ... synchronous git operations
```

### LangGraph invocation model

```python
# CLI entry point — use asyncio.run
async def run_pipeline(case_input: CaseInput, container: ServiceContainer):
    graph = build_ddk_graph()
    result = await graph.ainvoke(
        initial_state(case_input),
        context=container,
    )
    return result

# In cli.py
def run_command(image: Path, prompt: str, repo: Path):
    container = create_service_container()  # factory
    case_input = build_case_input(image, prompt, repo)
    result = asyncio.run(run_pipeline(case_input, container))
```

## Subgraph Composition

**Confidence:** HIGH — Verified against LangGraph v1.1.3.

### Current design: single flat graph (correct for MVP)

The 10-node pipeline is a single `StateGraph`. This is the right choice for v1.0:
- Linear flow with conditional branches is simple
- All nodes share the same `GraphState`
- No need for state mapping between subgraphs

### When to introduce subgraphs (v2.0+)

Subgraphs make sense when:
1. **Design Studio** is added (separate state, different flow)
2. **Multi-case batching** needs parallel execution
3. **The auto-fix loop** becomes complex enough to warrant isolation

**How subgraph composition works in LangGraph v1.1.3:**

```python
# Compiled subgraph can be used as a node in parent graph
inner_compiled = inner_graph.compile()
outer_graph.add_node("inner_step", inner_compiled)

# context_schema propagates: if parent and child share the same
# context_schema type, the parent's context is available in child nodes.
```

**Key constraint:** Inner/outer states must share overlapping keys for data to flow. LangGraph maps by key name — `inner_state["value"]` ←→ `outer_state["value"]`.

### v2.0 subgraph plan (informational)

```
MainGraph
├── delivery_subgraph (current 10 nodes)
├── design_studio_subgraph (interviewer → doc_generator → quality_gate)
└── handoff node (DesignHandoffPackage → CaseInput)
```

## Data Flow

### Full Pipeline Data Flow

```
CLI: CaseInput
    ↓
ingest_node ──→ GraphState.case_input
    ↓
repo_scan_node ──→ GraphState.repo_profile
    ↓
intent_extract_node ──→ GraphState.intent_graph     [LLM call]
    ↓
plan_node ──→ GraphState.generation_plan             [LLM call]
    ↓
generate_node ──→ GraphState.generated_artifacts     [LLM call]
    ↓
normalize_node ──→ GraphState.normalization_report + patched artifacts
    ↓
runtime_validate_node ──→ GraphState.runtime_validation_report
    ↓ (conditional)
    ├─ pass → visual_regress_node ──→ GraphState.visual_regression_report
    │   ├─ pass → certify_node
    │   └─ fail → auto_fix_node
    └─ fail → auto_fix_node ──→ GraphState.fix_attempts (appended)
                    ↓
                    └─ back to runtime_validate (retry loop)
    ↓
certify_node ──→ GraphState.scorecard + release_decision + evidence_pack
    ↓
END (terminal_state: certified-ready | certified-blocked | manual-review-required)
```

### State Update Pattern

Every node returns a `dict` with only changed fields. LangGraph merges this into `GraphState`. Nodes must **never mutate** input state directly.

```python
# ✅ Correct — return delta dict
return {
    "repo_profile": profile,
    "current_node": "repo_scan",
}

# ❌ Wrong — mutating state
state["repo_profile"] = profile  # LangGraph won't track this
return state
```

### List Accumulation Pattern

For fields like `llm_call_records` and `fix_attempts`, nodes must return the full new list (append to existing):

```python
return {
    "llm_call_records": state["llm_call_records"] + [record.call_id],
    "fix_attempts": state["fix_attempts"] + [attempt],
}
```

Alternatively, use `Annotated[list, operator.add]` in `GraphState` for automatic accumulation — but this requires switching from `TypedDict` to using annotations. **Recommendation:** Stick with explicit accumulation for v1.0 (matches design docs, clearer intent).

## Integration Points Between Nodes and Services

### Node → Service → Adapter Dependency Map

| Node | Primary Service(s) | Required Adapters |
|------|-------------------|-------------------|
| `ingest` | (none — validation only) | `filesystem`, `workspace` |
| `repo_scan` | `RepoConventionScanner` | `filesystem` |
| `intent_extract` | `SemanticIntentExtractor` | `llm`, `model_router`, `recorder` |
| `plan` | `GenerationPlanner`, `DesignSystemInferencer` | `llm`, `model_router`, `recorder` |
| `generate` | `CodeGenerator`, `ContextPackBuilder` | `llm`, `model_router`, `recorder`, `filesystem` |
| `normalize` | `OutputNormalizer` | `filesystem` (optionally `llm` for complex fixes) |
| `runtime_validate` | `RuntimeValidationAggregator`, `FailureClassifier` | `sandbox`, `build_runner`, `browser`, `filesystem` |
| `visual_regress` | `VisualRegressionService` | `browser`, `screenshot_diff`, `sandbox` |
| `auto_fix` | `AutoFixPlanner`, `RetryBudgetController` | `llm`, `model_router`, `recorder`, `filesystem` |
| `certify` | `BenchmarkScorecardService`, `ReleaseDecisionService`, `EvidencePackBuilder` | `workspace`, `filesystem` |

### Cross-Cutting Dependencies

| Concern | Where Used | Adapter/Service |
|---------|-----------|-----------------|
| LLM call recording | `intent_extract`, `plan`, `generate`, `auto_fix` | `LLMCallRecorder` (wraps all LLM calls) |
| Cost tracking | Same as above | `CostTracker` |
| Model selection | Same as above | `ModelRouter` (node→model mapping) |
| Workspace artifacts | All nodes | `WorkspaceManager` |
| Error boundary | All nodes | `_node_wrapper` |

## Suggested Build Order

Build order is determined by import dependencies, testability, and the "can I run this node in isolation?" principle.

### Phase 0: Foundation (no LangGraph yet)

Build the layers that everything depends on, bottom-up:

```
Step 1: models/_base.py + models/input.py + models/repo.py
        → Contract tests: test_case_input_schema.py
        → Why first: every other layer imports from models/

Step 2: adapters/llm/base.py (Protocol) + adapters/llm/fake.py
        adapters/filesystem.py (Protocol + impl)
        adapters/git.py (Protocol + impl)
        → Unit tests: Protocol compliance
        → Why: services need adapter Protocols to type-check

Step 3: graph/state.py (GraphState TypedDict + initial_state)
        graph/context.py (ServiceContainer dataclass)
        → Contract tests: test_graph_state_schema.py
        → Why: nodes need these to compile

Step 4: workspace/manager.py + workspace/checkpoint.py
        → Integration tests: test_init_workspace.py
        → Why: ingest_node needs workspace

Step 5: graph/nodes/_wrapper.py
        → Unit tests: error → terminal_state mapping
        → Why: every node registration uses this
```

### Phase 1: First Runnable Node (ingest)

```
Step 6: graph/nodes/ingest.py
        → Integration test: ingest with real filesystem
        → First node that can run in graph context

Step 7: graph/builder.py (ingest only, single-node graph)
        graph/edges.py (stub)
        → Integration test: build graph, invoke with ingest only
        → Validates: context_schema injection works end-to-end
```

### Phase 2: Linear Chain (ingest → repo_scan → intent_extract → plan)

```
Step 8:  services/repo_scanner.py + models/repo.py (full)
         graph/nodes/repo_scan.py
         → Fixture: react-vite-ts repo fixture
         → Tests: scan fixture → RepoProfile validation

Step 9:  models/intent.py (full) + models/llm.py
         services/intent_extractor.py
         adapters/llm/recorder.py + adapters/llm/router.py
         graph/nodes/intent_extract.py
         → Tests: FakeLLM → IntentGraph validation

Step 10: models/generation.py
         services/generation_planner.py + services/design_inferencer.py
         services/context_pack_builder.py
         graph/nodes/plan.py
         → Tests: FakeLLM → GenerationPlan validation

Step 11: builder.py (4-node linear chain)
         → Integration test: ingest→repo_scan→intent→plan with FakeLLM
```

### Phase 3: Generation + Normalization

```
Step 12: services/code_generator.py
         graph/nodes/generate.py
         → Tests: FakeLLM → GeneratedArtifactSet validation

Step 13: models/normalization.py
         services/normalizer.py
         graph/nodes/normalize.py
         → Tests: drift fixtures → NormalizationReport

Step 14: builder.py (6-node chain, ingest through normalize)
```

### Phase 4: Validation Loop

```
Step 15: adapters/sandbox/ (worktree.py + policy.py)
         adapters/build_runner.py
         models/validation.py
         services/runtime_validator.py + services/failure_classifier.py
         graph/nodes/runtime_validate.py
         → Tests: broken-build fixtures in sandbox

Step 16: adapters/playwright_browser.py + adapters/screenshot_diff.py
         models/visual.py
         services/visual_regression.py
         graph/nodes/visual_regress.py
         → Tests: reference vs generated screenshot

Step 17: models/fix.py
         services/auto_fix_planner.py + services/retry_controller.py
         graph/nodes/auto_fix.py
         → Tests: non-improving detection, budget exhaustion

Step 18: graph/edges.py (all conditional routing)
         builder.py (full 10-node graph)
         → Integration: full loop with FakeLLM
```

### Phase 5: Certification + CLI

```
Step 19: models/scorecard.py + models/release.py + models/evidence.py
         services/benchmark_service.py + services/release_decision.py
         services/evidence_builder.py
         graph/nodes/certify.py

Step 20: cli.py (ddk run command)
         preflight/doctor.py
         → E2E: ddk run with fixture repo + FakeLLM → evidence pack
```

## Anti-Patterns

### Anti-Pattern 1: Service Instantiation Inside Nodes

**What people do:** `scanner = RepoConventionScanner()` inside the node function.
**Why it's wrong:** Untestable without monkeypatching. Environment-coupled. Every test needs real env vars.
**Do this instead:** Receive services via `runtime.context`, construct with injected adapters.

### Anti-Pattern 2: Domain Logic in Nodes

**What people do:** Write 50+ lines of business logic directly in `repo_scan_node`.
**Why it's wrong:** Logic tied to LangGraph, can't test without graph, can't reuse outside pipeline.
**Do this instead:** Node is 5-15 lines: unpack state → call service → pack result.

### Anti-Pattern 3: Passing Services Through GraphState

**What people do:** Add `llm_adapter: LLMAdapter` as a field in `GraphState`.
**Why it's wrong:** GraphState is a `TypedDict` for serializable data. Services aren't data. Breaks checkpointing. Breaks serialization.
**Do this instead:** Use `context_schema` / `Runtime` — designed exactly for this.

### Anti-Pattern 4: Sync Blocking in Async Nodes

**What people do:** Call `subprocess.run()` or `path.read_text()` directly in `async def` nodes.
**Why it's wrong:** Blocks the event loop. LangGraph runs nodes in asyncio; blocking defeats concurrency.
**Do this instead:** Use `asyncio.to_thread(subprocess.run, ...)` or `asyncio.create_subprocess_exec(...)`.

### Anti-Pattern 5: Importing Concrete Adapters in Services

**What people do:** `from ddk.adapters.llm.anthropic import AnthropicAdapter` inside a service.
**Why it's wrong:** Hard-couples service to Anthropic. Can't test without Anthropic SDK.
**Do this instead:** Service constructor takes `llm: LLMAdapter` (Protocol). Concrete choice lives in `ServiceContainer`.

## New Components Required (Not in Design Docs)

| Component | File | Purpose | Why Needed |
|-----------|------|---------|------------|
| `ServiceContainer` | `graph/context.py` | Dataclass holding all adapters/services for DI | LangGraph `context_schema` requires a typed context object |
| `_node_wrapper` (updated) | `graph/nodes/_wrapper.py` | Error boundary with `Runtime[ServiceContainer]` | Design doc version doesn't forward runtime; needs update for DI |
| `FakeLLM` | `adapters/llm/fake.py` | Deterministic test double for LLM calls | Every test needs this; design docs mention "fake LLM provider" but don't spec it |
| `InMemoryFilesystem` | `adapters/filesystem.py` | Test double for file operations | Enables unit testing services without real filesystem |
| Container factory | `cli.py` or `factory.py` | `create_service_container()` from env/config | Assembles real adapters for production use |

## Sources

- **LangGraph v1.1.3** — Installed and verified against live API (2025-07-13)
  - `context_schema` parameter: `StateGraph.__init__` signature verified
  - `Runtime[ContextT]` injection: Tested with sync/async nodes
  - Subgraph context propagation: Verified parent→child flow
  - `functools.partial` + wrapper + `runtime` injection: Verified compatible
  - `add_sequence()` API: Verified for linear chains
- **LangGraph deprecation notices:** `config_schema` deprecated in favor of `context_schema` (v1.0+)
- **Design docs:** `04-system-design.md`, `13-project-structure.md`, `19-langgraph-builder.md`, `11-llm-interface.md`, `12-data-models.md`, `15-sandbox-design.md`
- **Python typing:** `Protocol` from `typing` module for structural subtyping (PEP 544)

---
*Architecture research for: ddalggak LangGraph Pipeline MVP*
*Researched: 2025-07-13*

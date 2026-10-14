# Codebase Structure

**Analysis Date:** 2024-12-19

## Directory Layout

```
project-root/
├── src/
│   └── ddk/                          # Main package
│       ├── __init__.py               # Package entrypoint, version
│       ├── __main__.py               # `python -m ddk`
│       ├── cli/                      # CLI commands, one module per group (run, demo, doctor, report, …)
│       ├── i18n/                     # Korean source strings + English table
│       ├── demo/                     # `ddk demo`: recorded model reply, bundled Vite project
│       ├── server.py                 # MCP server (design_new tool)
│       ├── installer.py              # Setup/installation helpers
│       │
│       ├── graph/                    # LangGraph pipeline orchestration
│       │   ├── __init__.py
│       │   ├── builder.py            # build_ddk_graph() — construct StateGraph
│       │   ├── state.py              # GraphState TypedDict, initial_state()
│       │   ├── context.py            # ServiceContainer DI dataclass
│       │   ├── router.py             # route_after_validate() — conditional routing
│       │   └── nodes/                # 10-node implementations
│       │       ├── __init__.py
│       │       ├── _wrapper.py       # node_wrapper() error boundary
│       │       ├── intake.py         # intake_node
│       │       ├── repo_scan.py      # repo_scan_node
│       │       ├── intent_extract.py # intent_extract_node
│       │       ├── design_system.py  # design_system_node
│       │       ├── plan.py           # plan_node
│       │       ├── generate.py       # generate_node
│       │       ├── normalize.py      # normalize_node
│       │       ├── validate.py       # validate_node
│       │       ├── autofix.py        # autofix_node
│       │       └── certify.py        # certify_node
│       │
│       ├── models/                   # Pydantic v2 data models (24 files)
│       │   ├── __init__.py           # Exports all models
│       │   ├── _base.py              # DDKBaseModel base class
│       │   ├── config.py             # DdalggakConfig
│       │   ├── errors.py             # Error classes
│       │   │
│       │   # Input & Analysis
│       │   ├── input.py              # CaseInput
│       │   ├── repo.py               # RepoProfile
│       │   ├── intent.py             # IntentGraph
│       │   │
│       │   # Design System Models
│       │   ├── design_system.py      # DesignSystem
│       │   ├── design_document.py    # Design document types
│       │   ├── design_package.py     # DesignPackage
│       │   ├── design_compliance.py  # Design compliance checks
│       │   ├── design_interview.py   # DesignInterview
│       │   ├── design_quality.py     # Design quality metrics
│       │   ├── design_requirement.py # Design requirements
│       │   │
│       │   # Generation & Artifacts
│       │   ├── generation.py         # GenerationPlan, GeneratedFile, GeneratedArtifactSet
│       │   ├── normalization.py      # NormalizationReport, ConventionFix
│       │   │
│       │   # Validation & Self-Healing
│       │   ├── validation.py         # RuntimeValidationReport, FailureRecord
│       │   ├── visual.py             # VisualRegressionReport
│       │   ├── fix.py                # FixAttempt
│       │   │
│       │   # Certification & Output
│       │   ├── scorecard.py          # Scorecard
│       │   ├── release.py            # ReleaseDecision
│       │   ├── evidence.py           # EvidencePack
│       │   │
│       │   # Supporting Models
│       │   ├── context_pack.py       # ContextPack, ContextChunk
│       │   ├── llm.py                # LLMCallRecord, LLMMetadata
│       │   └── visual.py             # VisualRegressionReport
│       │
│       ├── services/                 # Business logic layer (16 services)
│       │   ├── __init__.py
│       │   │
│       │   # Forward path (Phase 2–3)
│       │   ├── intake_processor.py           # IntakeProcessor
│       │   ├── repo_convention_scanner.py    # RepoConventionScanner
│       │   ├── semantic_intent_extractor.py # SemanticIntentExtractor
│       │   ├── design_system_inferencer.py   # DesignSystemInferencer
│       │   ├── generation_planner.py         # GenerationPlanner
│       │   ├── context_pack_builder.py       # ContextPackBuilder (deterministic)
│       │   ├── code_generator.py             # CodeGenerator
│       │   ├── output_normalizer.py          # OutputNormalizer
│       │   │
│       │   # Validation & self-healing (Phase 4)
│       │   ├── runtime_validator.py          # RuntimeValidator (orchestrates sandbox)
│       │   ├── failure_classifier.py         # FailureClassifier (taxonomy assignment)
│       │   ├── auto_fix_planner.py           # AutoFixPlanner (9-rule hybrid)
│       │   ├── rollback_controller.py        # RollbackController (git worktree mgmt)
│       │   │
│       │   # Certification (Phase 5)
│       │   ├── scorecard_calculator.py       # ScorecardCalculator
│       │   ├── release_gate.py               # ReleaseGate
│       │   ├── evidence_pack_builder.py      # EvidencePackBuilder
│       │   ├── case_artifact_store.py        # CaseArtifactStore
│       │   ├── pipeline_runner.py            # PipelineRunner — main orchestrator
│       │   └── [design_*.py]                 # Design studio services (separate concern)
│       │
│       ├── adapters/                 # Port & Adapter layer (7 Protocols + implementations)
│       │   ├── __init__.py
│       │   ├── filesystem.py         # FilesystemPort protocol
│       │   ├── git.py                # GitAdapter protocol
│       │   ├── local_git.py          # LocalGit — concrete git implementation
│       │   ├── build_runner.py       # BuildRunner protocol
│       │   ├── subprocess_build_runner.py  # SubprocessBuildRunner — npm/python runner
│       │   ├── playwright_browser.py # PlaywrightAdapter protocol
│       │   ├── null_playwright.py    # NullPlaywrightAdapter — headless fallback
│       │   ├── screenshot_diff.py    # ScreenshotDiffAdapter protocol
│       │   ├── screenshot_diff_local.py    # ScreenshotDiffLocal — SSIM implementation
│       │   │
│       │   ├── llm/                  # LLM adapters
│       │   │   ├── __init__.py
│       │   │   ├── base.py           # LLMAdapter protocol, Message, LLMResponse types
│       │   │   └── claude.py         # ClaudeAdapter — Anthropic SDK wrapper
│       │   │
│       │   └── sandbox/              # Sandbox execution
│       │       ├── __init__.py
│       │       ├── base.py           # SandboxAdapter protocol
│       │       ├── tempdir.py        # TempDirSandbox — git worktree-based
│       │       └── policy.py         # Sandbox execution policy (ENV_WHITELIST, FORBIDDEN_*)
│       │
│       ├── design/                   # Design Studio (separate AI workflow)
│       │   ├── __init__.py
│       │   ├── interviewer.py        # DesignInterviewer — interactive questions
│       │   ├── generator.py          # DesignGenerator — parallel doc generation
│       │   ├── writer.py             # DesignWriter — file output
│       │   └── templates.py          # Prompt templates for design docs
│       │
│       ├── workspace/                # Workspace management
│       │   ├── __init__.py
│       │   └── manager.py            # WorkspaceManager — .ddk/ directory lifecycle
│       │
│       ├── security/                 # Security utilities
│       │   ├── __init__.py
│       │   └── redact.py             # Secret redaction for logs
│       │
│       ├── logging/                  # Structured logging
│       │   ├── __init__.py
│       │   └── [config].py           # structlog configuration
│       │
│       ├── preflight/                # Environment checks
│       │   ├── __init__.py
│       │   └── doctor.py             # PreflightDoctor — ddk preflight command
│       │
│       └── assets/                   # Static assets
│           └── commands/             # Prompt templates by AI provider (Claude, Copilot, etc.)
│               ├── claude/
│               ├── copilot/
│               ├── cursor/
│               ├── gemini/
│               └── ...
│
├── tests/                            # Test directory
│   ├── conftest.py                   # pytest fixtures, test doubles
│   ├── test_models/                  # Model serialization tests
│   ├── test_services/                # Service unit & integration tests
│   ├── test_adapters/                # Adapter tests (using test doubles)
│   ├── test_nodes/                   # Node tests (with mocked services)
│   ├── test_graph/                   # Graph topology & E2E tests
│   ├── test_integration/             # Full pipeline E2E tests
│   └── fixtures/                     # Test data (sample repos, design images, etc.)
│
├── docs/                             # Documentation
│   ├── architecture/
│   ├── design/                       # Design specs (Phase 1–5 planning docs)
│   ├── api/                          # API reference
│   └── ...
│
├── pyproject.toml                    # Project metadata, dependencies, build config
├── uv.lock                           # Locked dependency versions (uv package manager)
├── .env.example                      # Environment variables template
└── .planning/                        # Planning & roadmap
    ├── ROADMAP.md                    # Phase 1–5 delivery roadmap
    ├── PROJECT.md                    # Project overview
    ├── codebase/                     # Codebase documentation (this directory)
    │   └── ARCHITECTURE.md, STRUCTURE.md
    └── phases/                       # Phase-specific design docs
```

## Directory Purposes

### `src/ddk/graph/` — LangGraph Orchestration

**Purpose:** State machine definition and node execution

**Contains:** 
- StateGraph topology (10 nodes, conditional routing)
- GraphState definition (19 fields)
- ServiceContainer (DI)
- Nodes directory (10 async functions)

**Key files:** `builder.py` (orchestration), `state.py` (state schema), `router.py` (routing logic), `nodes/_wrapper.py` (error boundary)

### `src/ddk/models/` — Data Contracts

**Purpose:** Define all data structures flowing through the pipeline

**Contains:** 24 Pydantic models, all inheriting from DDKBaseModel

**Patterns:** 
- All models immutable-by-convention (frozen=False but convention enforced)
- Validation via field_validator decorators
- Roundtrip serialization/deserialization tests
- No logic, only structure + validators

### `src/ddk/services/` — Business Logic

**Purpose:** Stateless orchestrators of adapters and models

**Contains:** 16 service classes; each handles one business capability

**Patterns:**
- Constructor injection (take adapters as params)
- Async methods (service.method())
- Return models (never raw dicts)
- No state mutation (return new instances)
- LLM calls and external I/O here, not in nodes

### `src/ddk/adapters/` — External Integration Points

**Purpose:** Abstract all I/O and external dependencies

**Contains:** 
- 7 Protocol definitions (interfaces)
- 10+ concrete implementations (and test doubles)
- Subprocess wrappers (build_runner, sandbox)

**Patterns:**
- @runtime_checkable Protocols (duck typing)
- Concrete adapters in subdirs (llm/, sandbox/)
- Test doubles have identical interface
- No business logic, only mechanical translation

### `src/ddk/nodes/` — Thin Request Handlers

**Purpose:** LangGraph node implementations (one per vertex)

**Contains:** 10 async functions following thin adapter pattern

**Pattern:**
```python
async def node_name(state: dict, **kwargs) -> dict:
    container = kwargs.get("context")
    service = ServiceClass(...)
    result = await service.method(state["field"])
    return {"result": result, "current_node": "name"}
```

### `src/ddk/design/` — Design Studio (Separate Workflow)

**Purpose:** Interactive AI-driven design document generation (NOT the delivery pipeline)

**Contains:** 
- DesignInterviewer (questions → model info)
- DesignGenerator (parallel LLM calls for 10 docs)
- DesignWriter (write to disk)
- Templates (prompt templates)

**Note:** Completely separate concern from delivery pipeline; used only by `ddk design new` CLI command and MCP server

## Key File Locations

### Entry Points

**CLI:** `src/ddk/cli/`
- `ddk doctor` / `ddk preflight` → PreflightDoctor
- `ddk design new <IDEA>` → DesignGenerator
- `ddk run <image>` → PipelineRunner
- `ddk demo` → `demo/runner.py`

**Server:** `src/ddk/server.py`
- MCP server exposing `design_new()` tool

**Programmatic:** `src/ddk/services/pipeline_runner.py`
- PipelineRunner.run_case(case_input) — main entry for batch/API usage

### Configuration

**Main config:** `src/ddk/models/config.py` — DdalggakConfig
- Reads from env vars: DDK_ANTHROPIC_API_KEY, DDK_LOG_LEVEL, DDK_CASE_DIR, etc.
- Validates at module load; raises error if critical vars missing

**Sandbox policy:** `src/ddk/adapters/sandbox/policy.py`
- ENV_WHITELIST, FORBIDDEN_READ_PATHS, FORBIDDEN_WRITE_PATHS
- Policy enforced by TempDirSandbox

### Core Logic

**Graph orchestration:** `src/ddk/graph/builder.py`
- build_ddk_graph() constructs the full 10-node StateGraph

**State management:** `src/ddk/graph/state.py`
- GraphState TypedDict (19 fields)
- initial_state(case_input) factory

**Routing logic:** `src/ddk/graph/router.py`
- route_after_validate() — determine next node (pass/fix_available/exhausted)
- Handles oscillation detection via failure_hash_history

**Node wrapper:** `src/ddk/graph/nodes/_wrapper.py`
- node_wrapper() error boundary
- ServiceContainer injection via LangGraph context

### Testing

**Fixtures:** `tests/conftest.py`
- FakeLLMAdapter, FakeSandboxAdapter, FakeGitAdapter, etc.
- Chaos fixtures (malformed JSON, timeout, etc.)

**Test structure:**
- `tests/test_models/` — Roundtrip serialization
- `tests/test_services/` — Service unit tests (with fakes)
- `tests/test_nodes/` — Node tests (with mocked services)
- `tests/test_graph/` — Graph topology, routing logic
- `tests/test_integration/` — Full E2E pipeline (with FakeLLM)

### Design System

**Models:** `src/ddk/models/design_*.py` (7 files)
- DesignSystem (tokens, spacing, typography)
- DesignDocument (SRS, PRD, Architecture, etc.)
- DesignPackage (10 docs bundled)
- DesignCompliance, DesignQuality, etc.

**Services:** `src/ddk/design/*.py`
- DesignInterviewer, DesignGenerator, DesignWriter
- Templates for 10 design document types

## Naming Conventions

### Files

**Pattern:** `snake_case.py` for all Python files

**Examples:**
- `intake_processor.py` — service class IntakeProcessor
- `repo_convention_scanner.py` — service class RepoConventionScanner
- `graph/nodes/design_system.py` — node function design_system_node

**Exceptions:**
- `_base.py` — base classes (private naming)
- `_wrapper.py` — internal utility module

### Classes

**Pattern:** `PascalCase` for all classes

**Suffixes:**
- `Adapter` — adapter implementations (ClaudeAdapter, LocalGit)
- `Processor`, `Scanner`, `Extractor` — services (IntakeProcessor, RepoConventionScanner)
- `Node` — LangGraph nodes (intake_node, validate_node) — actually functions, not classes
- `Protocol` — interfaces (@runtime_checkable)
- `Report`, `Result`, `Pack`, `Set` — output models (RuntimeValidationReport, FixAttempt)

### Functions

**Pattern:** `snake_case` for all functions

**Conventions:**
- Node functions: `{domain}_node()` (intake_node, generate_node)
- Service methods: `{verb}()` (process, scan, extract, generate, normalize, validate)
- Router function: `route_{condition}()` (route_after_validate)
- Wrapper: `node_wrapper()`, `_extract_context()`

### Variables & Parameters

**Pattern:** `snake_case` for variables

**TypedDict fields:** `snake_case` (case_id, repo_profile, llm_call_records)

**Model fields:** `snake_case` with Python conventions; pydantic populate_by_name=True for alternate naming

### Type Hints

**Pattern:** Full type hints throughout

**Examples:**
```python
async def run_case(self, case_input: CaseInput) -> dict[str, Any]:
    result: RuntimeValidationReport = await validator.run(state)
    return {"report": result}
```

## Where to Add New Code

### New Feature (End-to-End)

1. **Define models** → `src/ddk/models/{domain}.py`
   - New DDKBaseModel subclass(es) with validators
   - Add to `src/ddk/models/__init__.py` exports

2. **Define adapter protocols** (if external I/O needed) → `src/ddk/adapters/{domain}.py` or subdirectory
   - @runtime_checkable Protocol with async methods
   - Create at least one concrete implementation
   - Create test double (fake)

3. **Implement business logic** → `src/ddk/services/{domain}.py`
   - Stateless service class
   - Constructor DI for adapters
   - Async methods (not __call__)
   - Return models (never raw dicts)

4. **Add to graph** → `src/ddk/graph/`
   - Create node: `src/ddk/graph/nodes/{domain}.py`
   - Implement thin adapter pattern
   - Wrap with node_wrapper() in builder
   - Add edge(s) in builder.py

5. **Add to DI** → `src/ddk/graph/context.py`
   - Add service to ServiceContainer if needed
   - Update PipelineRunner to instantiate

6. **Add CLI** (if user-facing) → a module under `src/ddk/cli/` (register it in `cli/app.py`)
   - New @app.command() or subcommand; wrap user-facing text in `t()` and add its English entry
   - Call PipelineRunner or service directly

7. **Write tests** → `tests/test_{domain}/*.py`
   - Model roundtrip serialization
   - Service unit tests (with fakes)
   - Node tests (with mocked services)
   - Integration tests (if needed)

### New Service

**Template location:** `src/ddk/services/new_service.py`

```python
"""Module docstring — requirement reference (e.g., CODEGEN-01)."""

from __future__ import annotations

from typing import Any

from ddk.adapters.llm.base import LLMAdapter  # if needed
from ddk.models.input import SomeInputModel
from ddk.models.output import SomeOutputModel


class NewService:
    """One-line summary of what this service does."""

    def __init__(self, llm: LLMAdapter | None = None) -> None:
        """Initialize with injected dependencies."""
        self._llm = llm

    async def main_method(self, input_model: SomeInputModel) -> SomeOutputModel:
        """Main business logic method.

        Args:
            input_model: Input data structure.

        Returns:
            Computed output model.
        """
        # Implementation
        return SomeOutputModel(...)
```

### New Node

**Template location:** `src/ddk/graph/nodes/new_node.py`

```python
"""Node docstring — requirement reference (e.g., D-05)."""

from __future__ import annotations

from typing import Any

from ddk.graph.context import ServiceContainer
from ddk.services.new_service import NewService


async def new_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Thin adapter: reads state → calls service → writes state.

    Args:
        state: Current GraphState.
        **kwargs: LangGraph context injection.

    Returns:
        Partial state dict with updated fields.
    """
    container: ServiceContainer | None = kwargs.get("context")
    if container is None or container.llm is None:
        return {
            "terminal_state": "manual-review-required",
            "error_message": "LLM adapter not configured",
        }

    service = NewService(llm=container.llm)
    result = await service.main_method(state["input_field"])

    return {
        "output_field": result,
        "current_node": "new_node",
    }
```

Then add to builder:
```python
workflow.add_node("new_node", node_wrapper(new_node_node))
workflow.add_edge("previous_node", "new_node")
workflow.add_edge("new_node", "next_node")
```

### Utilities

**Shared helpers:** `src/ddk/services/` (if stateless) or `src/ddk/logging/` (if logging-related)

**Path convention:** Put in appropriate module, export from `__init__.py`

## Special Directories

### `.ddk/` (Generated at Runtime)

**Purpose:** Workspace directory for case execution

**Structure (created by WorkspaceManager.init()):**
```
.ddk/
├── cases/
│   └── {case_id}/
│       ├── input/
│       ├── output/
│       ├── validation/
│       └── artifacts/
├── logs/
└── schema_version.txt
```

**Generated:** Yes (never committed)

**Committed:** No

### `tests/fixtures/`

**Purpose:** Test data (sample repos, images, etc.)

**Examples:**
- `fixtures/sample_repos/react-todo/` — minimal React repo for integration tests
- `fixtures/design_images/` — sample design screenshots

**Generated:** No

**Committed:** Yes (small files; large binaries gitignored)

### `src/ddk/assets/commands/`

**Purpose:** Static AI prompt templates by provider

**Structure:**
```
assets/commands/
├── claude/
│   ├── design-srs.txt
│   ├── design-prd.txt
│   └── ...
├── copilot/
├── cursor/
└── ...
```

**Generated:** No

**Committed:** Yes

## Dependency Graph

```
models/
  └── (no dependencies except Pydantic)

adapters/
  ├── depends on: models
  └── (protocols, implementations)

services/
  ├── depends on: models, adapters
  └── (business logic)

graph/
  ├── depends on: models, adapters, services
  ├── state.py
  ├── context.py
  ├── router.py
  ├── builder.py
  └── nodes/
      └── depends on: services, graph/{state,context}

cli/, server.py
  ├── depends on: services, graph, models

tests/
  ├── depends on: everything (+ test doubles)
```

---

*Structure analysis: 2024-12-19*

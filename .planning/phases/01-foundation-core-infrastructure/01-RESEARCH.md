# Phase 1: Foundation & Core Infrastructure - Research

**Researched:** 2025-07-27
**Domain:** Python project scaffolding, Pydantic v2 data models, LangGraph DI, Protocol-based adapters, structured logging, workspace management, preflight doctor
**Confidence:** HIGH

## Summary

Phase 1 builds the complete foundation layer for ddalggak — a greenfield Python CLI project that requires zero existing code. The scope is well-defined by 10 design documents: project scaffolding (pyproject.toml, src layout, tool config), all 40+ Pydantic v2 models from `12-data-models.md`, 7 adapter Protocol definitions with 8 test doubles, ServiceContainer DI via LangGraph's `context_schema`, workspace management (`ddk init`), preflight doctor (`ddk doctor`), structured logging with secret redaction, and sandbox policy definitions.

**All critical patterns have been verified against the live environment:** LangGraph 1.1.2's `context_schema` + `Runtime[T]` injection works correctly with both sync and async nodes, including the `functools.partial(_node_wrapper, real_node)` error boundary pattern. Pydantic v2.12.5 is available. Python 3.14 is installed (above the >=3.12 requirement) and triggers a harmless Pydantic V1 deprecation warning from `langchain_core` that does not affect V2 functionality. The `structlog` 25.5.0 processor chain with `bind()` context propagation is confirmed working.

**Primary recommendation:** Follow the locked bottom-up TDD build order exactly (D-03): models → Protocols → fakes → DI → services → CLI. Every model gets a roundtrip serialization test. Every adapter Protocol gets a conformance test. The ServiceContainer smoke test validates DI wiring end-to-end via a minimal LangGraph graph.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** LangGraph `context_schema` + `Runtime[ServiceContainer]` 패턴을 채택한다. 설계 문서 원본의 `.from_config()` 팩토리 패턴은 사용하지 않는다. `ServiceContainer`는 `@dataclass`로 정의하며, 모든 어댑터 Protocol 인스턴스를 보유한다. 노드는 `runtime: Runtime[ServiceContainer]` 파라미터로 서비스에 접근한다. 테스트 시 fake 어댑터로 구성된 `ServiceContainer`를 주입하여 격리 테스트를 수행한다.
- **D-02:** `12-data-models.md`에 정의된 40+ Pydantic v2 모델을 전부 Phase 1에서 구현한다. 각 모델에 대해 roundtrip 직렬화 테스트(serialize → deserialize → assert equal)를 작성한다. 이를 통해 전체 시스템의 데이터 계약을 Phase 1에서 확립하고, 후속 Phase에서 모델 변경 없이 서비스/노드 구현에 집중한다.
- **D-03:** Bottom-up TDD를 적용한다. 빌드 순서: (1) Pydantic 모델 + roundtrip 테스트 → (2) 7개 어댑터 Protocol 정의 + 프로토콜 적합성 테스트 → (3) 8개 테스트 더블(FakeLLM 등) + fake 동작 테스트 → (4) ServiceContainer + DI 스모크 테스트 → (5) 워크스페이스/프리플라이트/로깅 서비스 + 서비스 단위 테스트 → (6) CLI 진입점(ddk doctor, ddk init) + CLI 통합 테스트.
- **D-04:** 하이브리드 접근을 채택한다. 읽기 작업(log, diff, status, blame)은 GitPython(`Repo` 객체) 사용, 쓰기/worktree/checkpoint 작업은 `asyncio.create_subprocess_exec()`로 git CLI를 직접 호출한다. GitPython `Repo` 객체는 반드시 명시적으로 `close()`하거나 context manager로 사용하여 프로세스 누수를 방지한다.

### Agent's Discretion
- 파일 내부 모듈 분할 (파일 당 모델 수, 유틸리티 분리 등)은 에이전트가 `13-project-structure.md`를 따라 자율 결정
- conftest.py 구조와 fixture 계층은 에이전트가 pytest best practice에 따라 자율 결정
- Ruff/Pyright 설정 세부 규칙은 에이전트가 `03-constraints-nfr.md` 범위 내에서 자율 결정

### Deferred Ideas (OUT OF SCOPE)
- Design Studio 그래프 (`build_design_studio_graph()`) — Phase 4+ / Milestone v2.0
- MCP 서버 통합 — Milestone v3.0
- Multi-provider LLM fallback 실제 호출 — Phase 2에서 구현 (Phase 1은 Protocol만 정의)
- Playwright 실제 브라우저 통합 — Phase 4
- SSIM 비주얼 비교 — Phase 4
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | 프로젝트 스캐폴딩 — pyproject.toml (uv), src 레이아웃, pytest/Ruff/Pyright 설정, CI 기본 구성 | `13-project-structure.md` provides complete layout; Stack research provides corrected pyproject.toml (typer>=0.15.0, dev deps split); Ruff/Pyright config from `03-constraints-nfr.md`; verified Python 3.14 + uv 0.10.4 available |
| INFRA-02 | Pydantic v2 데이터 모델 구현 — 40+ 모델 | `12-data-models.md` provides all 42 type definitions with fields, validators, enums; DDKBaseModel config verified; Pydantic 2.12.5 confirmed; roundtrip test pattern documented |
| INFRA-03 | 어댑터 Protocol 정의 — 7 Protocols | Architecture research documents all 7 Protocol definitions with method signatures; `10-multi-tool-adapter.md` + `09-ai-handoff.md` provide contracts |
| INFRA-04 | ServiceContainer + LangGraph context_schema DI | **LIVE VERIFIED** on LangGraph 1.1.2: `context_schema` param, `Runtime[T]` injection, `functools.partial` wrapper — all patterns confirmed working with both sync and async nodes |
| INFRA-05 | 테스트 인프라 — 8 fakes + chaos fixtures | `09-ai-handoff.md` §통합 테스트 모킹 전략 provides all 8 fake implementations with code; chaos fixture patterns (malformed JSON, rate limit, extra fields) documented in Pitfalls research |
| INFRA-06 | 구조화 로그 — structlog + RedactingFormatter + JSON | `33-security-privacy-governance.md` provides 7 regex patterns for RedactingFormatter; `04-system-design.md` specifies 12 log events; structlog 25.5.0 processor chain verified |
| INGEST-01 | Workspace Bootstrap — .ddk/ 디렉토리 구조, 스키마 버전 관리 | `14-cli-spec.md` §16 `ddk init` spec; `13-project-structure.md` §3 `.ddk/` structure; `12-data-models.md` §20 schema versioning rules |
| VALID-06 | Sandboxed Execution Policy — ENV_WHITELIST, FORBIDDEN_READ_PATHS | `04-system-design.md` §9 Sandbox Policy; `03-constraints-nfr.md` §6.6; policy definitions are data/config, not runtime enforcement in Phase 1 |
| CERT-04 | Reproducibility & LLM Call Metadata — LLMCallRecord | `12-data-models.md` §11 LLMCallRecord with all fields defined; model-only in Phase 1, actual recording in Phase 2 |
| CERT-05 | Preflight Doctor & Guided Setup | `14-cli-spec.md` §1 `ddk preflight` spec with check items, exit codes, output format; `05-adr-set.md` ADR-018 mandates preflight before run |
</phase_requirements>

## Standard Stack

### Core (Phase 1 Runtime Dependencies)

| Library | Verified Version | Purpose | Why Standard |
|---------|-----------------|---------|--------------|
| `pydantic` | 2.12.5 (installed) | 40+ data model contracts | Locked stack; v2 `model_dump_json`/`model_validate_json` for roundtrip |
| `pydantic-settings` | 2.13.1 (installed) | `DdalggakConfig(BaseSettings)` env loading | Required by `12-data-models.md` §19 — DdalggakConfig extends BaseSettings |
| `langgraph` | 1.1.2 (installed) | `StateGraph(context_schema=...)` for DI | Locked stack; `context_schema` + `Runtime[T]` verified working |
| `typer` | ≥0.15.0 | CLI framework (`ddk doctor`, `ddk init`) | Locked stack; brings `rich` transitively (no separate pin needed) |
| `structlog` | 25.5.0 (installed) | JSON structured logging + `bind()` context | ADR-014; wraps stdlib handlers; zero runtime deps |
| `gitpython` | 3.1.46 (installed) | Git adapter (read ops: log, diff, status) | D-04 decision; hybrid with subprocess for writes |

### Dev Dependencies (Phase 1)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | ≥8.0.0 | Test runner | All testing |
| `pytest-asyncio` | ≥0.23.0 | Async test support | Async node/adapter tests; `asyncio_mode = "auto"` |
| `pytest-cov` | ≥5.0.0 | Coverage reporting | CI coverage gates |
| `pytest-mock` | ≥3.14.0 | `mocker` fixture | Adapter/service mocking |
| `ruff` | ≥0.5.0 | Linting + formatting | Pre-commit, CI |
| `pyright` | ≥1.1.380 | Static type checking | CI, `typeCheckingMode = "strict"` |

### Not Needed in Phase 1

| Library | Why NOT |
|---------|---------|
| `anthropic` / `openai` | Phase 1 defines Protocol only; actual SDK usage in Phase 2 |
| `playwright` | Phase 1 defines Protocol only; browser automation in Phase 4 |
| `pillow` / `scikit-image` | No image processing in Phase 1 |
| `mcp` | Out of scope for v1.0 |
| `pydantic-settings` — WAIT | **Actually needed** — `DdalggakConfig` in `12-data-models.md` explicitly extends `pydantic_settings.BaseSettings`. Include it. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| structlog | stdlib logging only | stdlib works but requires manual context binding; structlog's `bind()` is ideal for per-node context in LangGraph |
| pydantic-settings | os.environ | Stack research recommended os.environ but design doc explicitly uses BaseSettings — follow the design doc |

**Installation (Phase 1 only):**
```bash
uv init
uv add pydantic pydantic-settings langgraph typer structlog gitpython
uv add --dev pytest pytest-asyncio pytest-cov pytest-mock ruff pyright
```

## Architecture Patterns

### Recommended Project Structure (Phase 1 Scope)

```
ddalggak/
├── pyproject.toml                ← hatchling build backend
├── src/
│   └── ddk/
│       ├── __init__.py           ← version = "0.1.0"
│       ├── cli.py                ← Typer app (ddk doctor, ddk init only)
│       │
│       ├── models/               ← ALL 40+ Pydantic v2 models
│       │   ├── __init__.py       ← re-exports for convenience
│       │   ├── _base.py          ← DDKBaseModel with ConfigDict
│       │   ├── input.py          ← CaseInput
│       │   ├── repo.py           ← RepoProfile, NamingRules, FileLayoutRules, DesignTokens
│       │   ├── intent.py         ← IntentGraph, LayoutRegion, BoundingBox, etc.
│       │   ├── generation.py     ← GenerationPlan, GenerationNode, GeneratedFile, etc.
│       │   ├── normalization.py  ← NormalizationReport, ConventionFix
│       │   ├── validation.py     ← RuntimeValidationReport, FailureRecord, FAILURE_TAXONOMY
│       │   ├── visual.py         ← VisualRegressionReport, MismatchRegion
│       │   ├── fix.py            ← FixAttempt
│       │   ├── scorecard.py      ← Scorecard
│       │   ├── release.py        ← ReleaseDecision, BlockerItem
│       │   ├── llm.py            ← LLMCallRecord
│       │   ├── evidence.py       ← EvidencePack
│       │   ├── errors.py         ← DDKError, ErrorChain, ErrorCategory, ErrorSeverity
│       │   ├── config.py         ← DdalggakConfig(BaseSettings), LLMProvider
│       │   ├── design_interview.py   ← InterviewTurn
│       │   ├── design_requirement.py ← DesignRequirement
│       │   ├── design_document.py    ← DesignDocument
│       │   ├── design_compliance.py  ← StandardsComplianceResult, ComplianceCheckItem
│       │   ├── design_quality.py     ← QualityGateScore, QualityAxisScore
│       │   └── design_package.py     ← DesignPackageManifest
│       │
│       ├── graph/                ← LangGraph orchestration skeleton
│       │   ├── __init__.py
│       │   ├── state.py          ← GraphState TypedDict + initial_state()
│       │   ├── context.py        ← ServiceContainer @dataclass
│       │   ├── builder.py        ← build_ddk_graph() skeleton
│       │   └── nodes/
│       │       ├── __init__.py
│       │       └── _wrapper.py   ← _node_wrapper error boundary
│       │
│       ├── adapters/             ← Protocol definitions + stub files
│       │   ├── __init__.py
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── base.py       ← LLMAdapter Protocol, Message, LLMResponse, LLMCallConfig
│       │   │   ├── recorder.py   ← LLMCallRecorder (interface only)
│       │   │   ├── router.py     ← ModelRouter (interface only)
│       │   │   └── cost_tracker.py ← CostTracker (interface only)
│       │   ├── filesystem.py     ← FilesystemPort Protocol + FilesystemAdapter impl
│       │   ├── git.py            ← GitAdapter Protocol
│       │   ├── sandbox/
│       │   │   ├── __init__.py
│       │   │   ├── base.py       ← SandboxAdapter Protocol
│       │   │   └── policy.py     ← CommandAllowlist, PathPolicy, ENV_WHITELIST
│       │   ├── build_runner.py   ← BuildRunner Protocol
│       │   ├── playwright_browser.py ← PlaywrightAdapter Protocol (stub)
│       │   └── screenshot_diff.py    ← ScreenshotDiffAdapter Protocol (stub)
│       │
│       ├── workspace/            ← Workspace management
│       │   ├── __init__.py
│       │   └── manager.py        ← WorkspaceManager
│       │
│       ├── preflight/            ← Environment checks
│       │   ├── __init__.py
│       │   └── doctor.py         ← PreflightDoctor
│       │
│       ├── security/             ← Redaction
│       │   ├── __init__.py
│       │   └── redact.py         ← REDACT_PATTERNS, redact_string, redact_dict
│       │
│       └── logging/              ← Structured logging setup
│           ├── __init__.py
│           └── setup.py          ← configure_logging(), RedactingProcessor
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py               ← Shared fixtures (test_config, sample models, fake container)
│   ├── unit/
│   │   ├── __init__.py
│   │   └── models/               ← Roundtrip tests for all 40+ models
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_init_workspace.py
│   │   ├── test_preflight_doctor_integration.py
│   │   └── test_di_smoke.py      ← ServiceContainer + graph smoke test
│   ├── contract/
│   │   ├── __init__.py
│   │   ├── test_graph_state_schema.py
│   │   └── test_state_no_mutation.py
│   └── fakes/                    ← 8 test double implementations
│       ├── __init__.py
│       ├── fake_llm_adapter.py
│       ├── fake_sandbox.py
│       ├── fake_playwright_adapter.py
│       ├── fake_subprocess.py
│       ├── fake_filesystem.py
│       ├── fake_fallback_chain.py
│       ├── fake_rollback.py
│       └── fake_cost_tracker.py
│
└── fixtures/                     ← Test fixture data
    └── repos/
        └── react-vite-ts/        ← Minimal fixture repo structure
```

### Pattern 1: DDKBaseModel with Strict Config

**What:** All models extend `DDKBaseModel` with `extra="forbid"` to catch schema drift early.
**When to use:** Every Pydantic model in the project.
**Source:** `12-data-models.md`

```python
from pydantic import BaseModel, ConfigDict

class DDKBaseModel(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        populate_by_name=True,
        extra="forbid",  # Catches undefined fields immediately
    )
```

### Pattern 2: Roundtrip Serialization Test

**What:** Every model must pass serialize → deserialize → equality check.
**When to use:** Every model defined in `models/`.
**Source:** D-02 decision, Pitfall 9 (Pydantic serialization breaks)

```python
def test_case_input_roundtrip():
    original = CaseInput(
        case_id="C-001",
        image_paths=[Path("img.png")],
        prompt="test prompt",
        repo_path=Path("/tmp/repo"),
    )
    json_str = original.model_dump_json()
    restored = CaseInput.model_validate_json(json_str)
    assert original == restored
```

**⚠️ Path serialization:** `Path` objects serialize as strings in `model_dump_json()` but as `Path` objects in `model_dump()`. The roundtrip test catches this. If needed, add `@field_serializer` for Path fields.

### Pattern 3: Protocol-Based Adapter with Structural Typing

**What:** Use `typing.Protocol` for all adapters. Concrete implementations and fakes satisfy the Protocol structurally (no inheritance required).
**When to use:** All 7 adapters.
**Source:** Architecture research, Pattern 1

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMAdapter(Protocol):
    async def complete(self, messages: list[Message], config: LLMCallConfig) -> LLMResponse: ...
    async def complete_structured(self, messages: list[Message], config: LLMCallConfig, output_schema: type) -> LLMResponse: ...

# Test that fake satisfies Protocol
def test_fake_llm_satisfies_protocol():
    fake = FakeLLMAdapter(responses={})
    assert isinstance(fake, LLMAdapter)
```

### Pattern 4: ServiceContainer as @dataclass with context_schema

**What:** `ServiceContainer` is a `@dataclass` holding all adapter instances. Injected via `context_schema` parameter on `StateGraph`.
**When to use:** All graph construction and invocation.
**Source:** D-01 decision, Architecture research (VERIFIED on LangGraph 1.1.2)

```python
from dataclasses import dataclass
from langgraph.graph import StateGraph
from langgraph.runtime import Runtime

@dataclass
class ServiceContainer:
    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    # ... all 7 adapters + cross-cutting concerns

# Graph construction
workflow = StateGraph(GraphState, context_schema=ServiceContainer)

# Node signature
async def some_node(state: GraphState, runtime: Runtime[ServiceContainer]) -> dict:
    llm = runtime.context.llm  # Type-safe access
    ...

# Invocation
result = await graph.ainvoke(initial_state, context=container)
```

### Pattern 5: Error Boundary Wrapper with functools.partial

**What:** All nodes wrapped in `_node_wrapper` that catches OS/validation/timeout errors. Uses `functools.partial` to preserve LangGraph's `Runtime` injection.
**When to use:** Every node registration in `builder.py`.
**Source:** Architecture research (VERIFIED: `functools.partial(_node_wrapper, real_node)` correctly preserves Runtime parameter injection)

```python
import functools

async def _node_wrapper(
    node_fn: Callable,
    state: GraphState,
    runtime: Runtime[ServiceContainer],
) -> dict:
    try:
        return await node_fn(state, runtime)
    except (OSError, PermissionError) as e:
        return {"terminal_state": "manual-review-required", "error_message": str(e)}
    # ... other exception handlers

# Registration
workflow.add_node("repo_scan", functools.partial(_node_wrapper, repo_scan_node))
```

### Pattern 6: structlog with RedactingProcessor

**What:** structlog wraps stdlib logging with secret redaction processor and JSON output.
**When to use:** All logging throughout the application.
**Source:** `33-security-privacy-governance.md`, `14-cli-spec.md`

```python
import structlog
from ddk.security.redact import redact_string

def RedactingProcessor(logger, method_name, event_dict):
    for key, value in event_dict.items():
        if isinstance(value, str):
            event_dict[key] = redact_string(value)
    return event_dict

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        RedactingProcessor,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

# Usage in nodes
log = structlog.get_logger().bind(node="ingest", case_id=state["case_id"])
log.info("workspace_initialized", path=str(workspace_path))
```

### Anti-Patterns to Avoid

- **`state["list"].append()`:** NEVER mutate LangGraph state in-place. Always use `state["list"] + [new_item]` — Pitfall #1 (state mutation corruption)
- **`.from_config()` factory methods:** D-01 explicitly rejects this. Use constructor injection via `ServiceContainer`
- **GitPython `Repo` without close:** Always use `with git.Repo(path) as repo:` or explicit `repo.close()` — D-04 and Pitfall #4 (process leaks)
- **`model_dump()` for JSON serialization:** Use `model_dump_json()` consistently, never `json.dumps(model_dump())` — Pitfall #9 (Path serialization mismatch)
- **Importing from wrong layers:** `models/` depends on nothing; `adapters/` depends on `models/`; `services/` depends on `models/` + `adapters/`; `graph/` depends on all below. Never import upward.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Secret redaction in logs | Custom string scanning | structlog processor + 7 regex patterns from `33-security-privacy-governance.md` | Edge cases in regex matching, recursive dict traversal depth limits |
| Env var config loading | Manual `os.environ.get()` | `pydantic-settings` `BaseSettings` with `DDK_` prefix | Design doc requires it; handles type coercion, defaults, .env files |
| JSON structured logging | Custom `logging.Formatter` subclass | structlog's `JSONRenderer` processor | Handles nested dicts, datetime serialization, unicode |
| CLI framework | argparse | Typer (locked stack) | Brings rich integration, type-safe params, automatic help |
| Protocol conformance testing | Manual method-by-method checks | `@runtime_checkable` Protocol + `isinstance()` | One-line test, catches method signature mismatches at runtime |

**Key insight:** Phase 1 is pure scaffolding — all logic is definitions, contracts, and tests. Resist the temptation to pre-implement service business logic. Define Protocols and stubs, not implementations.

## Common Pitfalls

### Pitfall 1: LangGraph State Mutation Corruption
**What goes wrong:** Nodes that do `state["fix_attempts"].append(attempt)` corrupt shared state across the graph.
**Why it happens:** Python mutable default gotcha. TypedDict list fields are shared references.
**How to avoid:** Always return new lists: `return {"fix_attempts": state["fix_attempts"] + [new_attempt]}`. Add a contract test `test_state_no_mutation.py` that verifies no node mutates input state.
**Warning signs:** Tests pass individually but fail in sequence; state values "bleed" between runs.

### Pitfall 2: Pydantic v2 Path Serialization Mismatch
**What goes wrong:** `Path` objects serialize as strings in `model_dump_json()` but as `Path` in `model_dump()`. Models with `list[Path]` fields (CaseInput.image_paths) fail roundtrip if deserialization expects `Path` but gets `str`.
**Why it happens:** Pydantic v2's JSON serialization converts `Path` to `str` by default. `model_validate_json()` then needs to parse strings back to `Path`.
**How to avoid:** Write roundtrip tests (serialize → deserialize → assert equal) for ALL models. Pydantic v2 handles `Path` ↔ `str` coercion automatically in `model_validate_json()`, but verify with tests. If issues arise, add `@field_serializer` for Path fields.
**Warning signs:** `TypeError: Object of type PosixPath is not JSON serializable` during evidence pack save.

### Pitfall 3: DdalggakConfig Requires pydantic-settings
**What goes wrong:** `DdalggakConfig` in `12-data-models.md` extends `pydantic_settings.BaseSettings`. If pydantic-settings is not installed, import fails.
**Why it happens:** Stack research (STACK.md) recommended against pydantic-settings as "overkill", but the design doc explicitly uses it. The data model is authoritative.
**How to avoid:** Include `pydantic-settings` in dependencies. Follow the design doc.
**Warning signs:** `ImportError: No module named 'pydantic_settings'` when importing config model.

### Pitfall 4: Python 3.14 Pydantic V1 Deprecation Warning
**What goes wrong:** `langchain_core` imports Pydantic V1 compatibility layer, triggering `UserWarning: Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater`.
**Why it happens:** LangGraph's transitive dependency `langchain_core` still references Pydantic V1 compatibility module.
**How to avoid:** The warning is harmless — all ddalggak code uses Pydantic V2 only. Suppress in pytest via `filterwarnings` in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
filterwarnings = [
    "ignore:Core Pydantic V1:UserWarning",
]
```
**Warning signs:** Noisy test output; may confuse developers into thinking Pydantic V2 features don't work.

### Pitfall 5: GitPython Repo Process Leaks
**What goes wrong:** `git.Repo()` spawns git processes that aren't cleaned up if the Repo object isn't properly closed.
**Why it happens:** GitPython's `Repo.__del__` is unreliable in async contexts.
**How to avoid:** Always use `with git.Repo(path) as repo:` context manager or explicit `repo.close()`. D-04 decision explicitly mandates this.
**Warning signs:** Resource warnings in tests; increasing number of git processes after test suite runs.

### Pitfall 6: Missing Roundtrip Tests for Nested Models
**What goes wrong:** Models like `EvidencePack` reference `ErrorChain` which has `list[DDKError]`. Deep nesting with optional fields, enums, and datetime can fail silently.
**Why it happens:** Pydantic v2's `frozen=False` + `validate_assignment=True` means any accidental field assignment triggers full re-validation.
**How to avoid:** Every model gets its own roundtrip test. Use `@pytest.mark.parametrize` with edge cases: empty lists, `None` optionals, max-length strings, boundary floats.
**Warning signs:** Tests pass for simple models but `EvidencePack` or `DesignPackageManifest` roundtrip fails.

## Code Examples

### Complete DDKBaseModel Definition
```python
# src/ddk/models/_base.py
from __future__ import annotations
from pydantic import BaseModel, ConfigDict

class DDKBaseModel(BaseModel):
    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        populate_by_name=True,
        extra="forbid",
    )
```
Source: `12-data-models.md`

### GraphState TypedDict
```python
# src/ddk/graph/state.py
from typing import TypedDict, Optional
from ddk.models.input import CaseInput
from ddk.models.repo import RepoProfile
# ... all model imports

class GraphState(TypedDict):
    case_id: str
    case_input: Optional[CaseInput]
    repo_profile: Optional[RepoProfile]
    intent_graph: Optional[IntentGraph]
    generation_plan: Optional[GenerationPlan]
    generated_artifacts: Optional[GeneratedArtifactSet]
    normalization_report: Optional[NormalizationReport]
    runtime_validation_report: Optional[RuntimeValidationReport]
    visual_regression_report: Optional[VisualRegressionReport]
    fix_attempts: list[FixAttempt]
    scorecard: Optional[Scorecard]
    release_decision: Optional[ReleaseDecision]
    evidence_pack: Optional[EvidencePack]
    design_handoff: Optional[DesignHandoffPackage]
    retry_budget_remaining: int
    current_node: str
    terminal_state: Optional[str]
    error_message: Optional[str]
    pre_run_checkpoint_ref: Optional[str]
    llm_call_records: list[str]
    total_cost_usd: float
    reproducibility_seed: Optional[int]

def initial_state(case_input: CaseInput) -> GraphState:
    return {
        "case_id": case_input.case_id,
        "case_input": case_input,
        "repo_profile": None,
        "intent_graph": None,
        # ... all None/empty defaults
        "fix_attempts": [],
        "retry_budget_remaining": 3,
        "current_node": "start",
        "terminal_state": None,
        "error_message": None,
        "pre_run_checkpoint_ref": None,
        "llm_call_records": [],
        "total_cost_usd": 0.0,
        "reproducibility_seed": None,
    }
```
Source: `13-project-structure.md` §2

### ServiceContainer @dataclass
```python
# src/ddk/graph/context.py
from __future__ import annotations
from dataclasses import dataclass
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.filesystem import FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter
from ddk.adapters.build_runner import BuildRunner

@dataclass
class ServiceContainer:
    """Run-scoped DI container injected into every LangGraph node."""
    llm: LLMAdapter
    filesystem: FilesystemPort
    git: GitAdapter
    sandbox: SandboxAdapter
    browser: PlaywrightAdapter
    screenshot_diff: ScreenshotDiffAdapter
    build_runner: BuildRunner
```
Source: Architecture research, verified against LangGraph 1.1.2

### Sandbox Policy Definitions
```python
# src/ddk/adapters/sandbox/policy.py

ENV_WHITELIST: frozenset[str] = frozenset({
    "PATH", "HOME", "USER", "LANG", "TERM",
    "NODE_ENV", "npm_config_cache",
    "DDK_SANDBOX_MODE", "DDK_LOG_LEVEL",
})

FORBIDDEN_READ_PATHS: list[str] = [
    "~/.ssh/",
    "~/.aws/",
    "~/.config/gcloud/",
    "~/.gnupg/",
    "/etc/shadow",
    "/etc/passwd",
]

ALLOWED_COMMANDS: list[str] = [
    "npm", "npx", "pnpm", "yarn", "bun",
    "node", "tsc", "vite",
    "git",
]
```
Source: `04-system-design.md` §9, `03-constraints-nfr.md` §6.6

### Secret Redaction Patterns
```python
# src/ddk/security/redact.py
import re

REDACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("api_key",     re.compile(r"(sk-[a-zA-Z0-9]{20,})")),
    ("api_key",     re.compile(r"(sk-ant-[a-zA-Z0-9\-]{20,})")),
    ("api_key",     re.compile(r"(AIza[a-zA-Z0-9\-_]{35})")),
    ("bearer",      re.compile(r"(Bearer\s+[a-zA-Z0-9\-_.~+/]+=*)")),
    ("env_secret",  re.compile(r"([A-Z_]{3,}_(?:KEY|TOKEN|SECRET|PASSWORD|PASS)=\S+)")),
    ("private_key", re.compile(r"(-----BEGIN (?:RSA |EC )?PRIVATE KEY-----.*?-----END)", re.DOTALL)),
    ("jwt",         re.compile(r"(eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,})")),
]
REDACT_PLACEHOLDER = "[REDACTED]"
```
Source: `33-security-privacy-governance.md` §Redaction 구현 명세

### Preflight Doctor Check Items
```python
# src/ddk/preflight/doctor.py (structure)
PREFLIGHT_CHECKS = [
    {"name": "python_version", "min": "3.12"},
    {"name": "uv_installed"},
    {"name": "anthropic_api_key", "env": "DDK_ANTHROPIC_API_KEY"},
    {"name": "playwright_browser", "command": "playwright --version"},
    {"name": "node_installed", "command": "node --version"},
    {"name": "git_version", "min": "2.30"},
]
```
Source: `14-cli-spec.md` §1 `ddk preflight`

### FakeLLMAdapter (Primary Test Double)
```python
# tests/fakes/fake_llm_adapter.py
class FakeLLMAdapter:
    def __init__(self, responses: dict[str, dict] | None = None):
        self.responses = responses or {}
        self.call_log: list[dict] = []

    async def complete_structured(
        self, messages: list[dict], config, output_schema: type
    ) -> dict:
        key = self._extract_key(messages)
        self.call_log.append({"key": key, "messages": messages})
        if key not in self.responses:
            raise ValueError(f"FakeLLMAdapter: no fixture for key '{key}'")
        return self.responses[key]

    async def complete(self, messages, config):
        return await self.complete_structured(messages, config, type(None))

    def _extract_key(self, messages: list[dict]) -> str:
        for msg in messages:
            if msg.get("role") == "system":
                return msg["content"].split()[0].lower()
        return "default"
```
Source: `09-ai-handoff.md` §통합 테스트 모킹 전략

## 40+ Model Inventory (from 12-data-models.md)

Complete list of models to implement, grouped by module:

| Module | Models | Count |
|--------|--------|-------|
| `_base.py` | DDKBaseModel | 1 |
| `input.py` | CaseInput | 1 |
| `repo.py` | NamingRules, FileLayoutRules, DesignTokens, RepoProfile | 4 |
| `intent.py` | BoundingBox, LayoutRegion, PropValue, ComponentSpec, InteractionSpec, IntentGraph | 6 |
| `generation.py` | GenerationNode, GenerationPlan, GeneratedFile, GeneratedArtifactSet | 4 |
| `normalization.py` | ConventionFix, NormalizationReport | 2 |
| `validation.py` | FailureRecord, RuntimeValidationReport + FAILURE_TAXONOMY dict | 2 |
| `visual.py` | MismatchRegion, VisualRegressionReport | 2 |
| `fix.py` | FixAttempt | 1 |
| `scorecard.py` | Scorecard | 1 |
| `release.py` | BlockerItem, ReleaseDecision | 2 |
| `llm.py` | LLMCallRecord | 1 |
| `evidence.py` | EvidencePack | 1 |
| `errors.py` | ErrorCategory (Enum), ErrorSeverity (Enum), DDKError, ErrorChain | 4 |
| `config.py` | LLMProvider (Enum), DdalggakConfig(BaseSettings) | 2 |
| `design_interview.py` | InterviewTurn | 1 |
| `design_requirement.py` | DesignRequirement | 1 |
| `design_document.py` | DesignDocument | 1 |
| `design_compliance.py` | ComplianceCheckItem, StandardsComplianceResult | 2 |
| `design_quality.py` | QualityAxisScore, QualityGateScore | 2 |
| `design_package.py` | DesignPackageManifest | 1 |
| **TOTAL** | | **42** |

## 7 Adapter Protocols Inventory

| # | Protocol | Module | Key Methods | Phase 1 Scope |
|---|----------|--------|-------------|---------------|
| 1 | `LLMAdapter` | `adapters/llm/base.py` | `complete()`, `complete_structured()` | Protocol + FakeLLMAdapter |
| 2 | `FilesystemPort` | `adapters/filesystem.py` | `read_text()`, `write_text()`, `list_dir()`, `exists()` | Protocol + FilesystemAdapter (real) + InMemoryFilesystem (fake) |
| 3 | `GitAdapter` | `adapters/git.py` | `status()`, `diff()`, `log()`, `create_worktree()`, `remove_worktree()` | Protocol only (hybrid D-04) |
| 4 | `SandboxAdapter` | `adapters/sandbox/base.py` | `create()`, `cleanup()`, `run_command()` | Protocol + TempDirSandbox (fake) |
| 5 | `PlaywrightAdapter` | `adapters/playwright_browser.py` | `capture_screenshot()`, `get_console_errors()` | Protocol + FakePlaywrightAdapter |
| 6 | `ScreenshotDiffAdapter` | `adapters/screenshot_diff.py` | `compute_ssim()`, `generate_diff_image()` | Protocol only (impl in Phase 4) |
| 7 | `BuildRunner` | `adapters/build_runner.py` | `run()` (subprocess execution) | Protocol + FakeSubprocessRunner |

## 8 Test Doubles Inventory

| # | Test Double | Fake For | Key Behavior |
|---|-------------|----------|-------------|
| 1 | FakeLLMAdapter | LLMAdapter | Returns canned responses keyed by system prompt; records call log |
| 2 | TempDirSandbox | SandboxAdapter | Uses `tempfile.mkdtemp()` instead of git worktree; real file I/O |
| 3 | FakePlaywrightAdapter | PlaywrightAdapter | Returns configurable SSIM score and fixture screenshot path |
| 4 | FakeSubprocessRunner | BuildRunner | Returns pre-configured (returncode, stdout, stderr) tuples |
| 5 | InMemoryFilesystem | FilesystemPort | Stores files in `dict[str, str]`; no disk I/O |
| 6 | FakeFallbackChain | LLMFallbackChain | Simulates N provider failures then success |
| 7 | FakeRollbackController | RollbackController | In-memory checkpoint/rollback history |
| 8 | FakeCostTracker | CostTracker | Always returns 0.0 cost |

## pyproject.toml Configuration

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ddalggak"
version = "0.1.0"
description = "AI 코딩 워크플로우 — generate → validate → auto-fix closed loop"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.15.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.0.0",
    "langgraph>=1.0.0",
    "structlog>=24.0.0",
    "gitpython>=3.1.40",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.5.0",
    "pyright>=1.1.380",
]

[project.scripts]
ddk = "ddk.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/ddk"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
filterwarnings = [
    "ignore:Core Pydantic V1:UserWarning",
]

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "UP", "B", "C4", "SIM"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
```

**Key deviations from design doc `13-project-structure.md` pyproject.toml:**
- `typer[all]>=0.12.0` → `typer>=0.15.0` (rich is now a direct dep of typer, `[all]` extra removed)
- `mcp>=1.0.0` → REMOVED (out of scope v1.0)
- `ruff`, `pyright` → moved to `[dev]` (not runtime deps)
- `rich>=13.0.0`, `httpx>=0.27.0` → REMOVED (transitive via typer/anthropic, not needed in Phase 1)
- `anthropic`, `openai`, `playwright`, `pillow`, `scikit-image` → REMOVED from Phase 1 (Protocol-only; add in Phase 2+)
- `pydantic-settings>=2.0.0` → ADDED (required by DdalggakConfig)
- `langgraph>=1.0.0` → bumped from `>=0.2.0` (v1.x is current; context_schema stable)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `config_schema` on StateGraph | `context_schema` on StateGraph | LangGraph v0.6.0 | `config_schema` deprecated; use `context_schema` + `Runtime[T]` |
| Pydantic v1 `.dict()` / `.json()` | v2 `model_dump()` / `model_dump_json()` | Pydantic 2.0 | All model serialization must use v2 API |
| `typer[all]` extras | `typer` (plain) | Typer 0.12+ | Rich is now a direct dependency; `[all]` extra removed |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.14.0 | — |
| uv | Package management | ✓ | 0.10.4 | — |
| Node.js | Preflight check target | ✓ | 25.6.1 | — |
| npm | Preflight check target | ✓ | 11.9.0 | — |
| LangGraph | DI/orchestration | ✓ | 1.1.2 | — |
| Pydantic | Data models | ✓ | 2.12.5 | — |
| pydantic-settings | DdalggakConfig | ✓ | 2.13.1 | — |
| structlog | Logging | ✓ | 25.5.0 | — |
| GitPython | Git adapter | ✓ | 3.1.46 | — |

**Missing dependencies with no fallback:** None — all Phase 1 dependencies are available.

**⚠️ Python 3.14 Note:** Current Python is 3.14.0, which triggers a deprecation warning from `langchain_core` (transitive via `langgraph`). The warning is about Pydantic V1 compatibility and does NOT affect Pydantic V2 functionality. Suppress in pytest config. The project targets `>=3.12` so this is fine.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest ≥8.0.0 + pytest-asyncio ≥0.23.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (create in Wave 0) |
| Quick run command | `uv run pytest tests/unit/ -x --tb=short` |
| Full suite command | `uv run pytest --cov=ddk --cov-report=term-missing` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Project scaffolding, imports work | smoke | `uv run python -c "import ddk"` | ❌ Wave 0 |
| INFRA-02 | 40+ models roundtrip serialization | unit | `uv run pytest tests/unit/models/ -x` | ❌ Wave 0 |
| INFRA-03 | 7 Protocol definitions + conformance | unit | `uv run pytest tests/unit/test_protocols.py -x` | ❌ Wave 0 |
| INFRA-04 | ServiceContainer DI smoke | integration | `uv run pytest tests/integration/test_di_smoke.py -x` | ❌ Wave 0 |
| INFRA-05 | 8 fakes + chaos fixtures | unit | `uv run pytest tests/unit/test_fakes.py -x` | ❌ Wave 0 |
| INFRA-06 | structlog JSON + redaction | unit | `uv run pytest tests/unit/test_logging.py -x` | ❌ Wave 0 |
| INGEST-01 | Workspace .ddk/ init + schema version | integration | `uv run pytest tests/integration/test_init_workspace.py -x` | ❌ Wave 0 |
| VALID-06 | Sandbox policy definitions | unit | `uv run pytest tests/unit/test_sandbox_policy.py -x` | ❌ Wave 0 |
| CERT-04 | LLMCallRecord schema | contract | `uv run pytest tests/contract/test_llm_call_record_contract.py -x` | ❌ Wave 0 |
| CERT-05 | Preflight doctor checks | integration | `uv run pytest tests/integration/test_preflight_doctor_integration.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x --tb=short -q`
- **Per wave merge:** `uv run pytest --cov=ddk --cov-report=term-missing`
- **Phase gate:** Full suite green + Ruff + Pyright before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` — project definition with all deps
- [ ] `src/ddk/__init__.py` — package init with version
- [ ] `tests/conftest.py` — shared fixtures (test_config, sample model factories)
- [ ] Test directory structure: `tests/{unit,integration,contract,fakes}/`
- [ ] Ruff/Pyright config in pyproject.toml
- [ ] pytest config with `asyncio_mode = "auto"` and warning filters

## Open Questions

1. **DdalggakConfig: BaseSettings vs DDKBaseModel**
   - What we know: `12-data-models.md` §19 explicitly uses `pydantic_settings.BaseSettings` with env_prefix. This requires pydantic-settings.
   - What's unclear: Stack research recommended against pydantic-settings. Design doc is authoritative.
   - Recommendation: Follow the design doc — include pydantic-settings. The config model needs env var loading.

2. **LLM Adapter Protocol Method Signatures**
   - What we know: Architecture research shows `complete()` and `complete_structured()` with `Message`, `LLMCallConfig`, `LLMResponse` types. `09-ai-handoff.md` shows a different signature (`messages: list[dict]`).
   - What's unclear: Exact method signatures aren't 100% consistent across design docs.
   - Recommendation: Use the Architecture research pattern (`Message` dataclass, typed config) as it's more type-safe. The actual SDK integration in Phase 2 will finalize.

3. **DesignHandoffPackage Model**
   - What we know: `GraphState` references `DesignHandoffPackage` but it's not in the 42-model list from `12-data-models.md`.
   - What's unclear: Whether this model is defined elsewhere or needs to be created.
   - Recommendation: Define a minimal `DesignHandoffPackage` stub in `models/` (Phase 1 scope is all models). If design doc doesn't define it, create a placeholder with `case_id: str` and `package_ref: str | None`.

## Sources

### Primary (HIGH confidence)
- `docs/design/12-data-models.md` — Complete 42 model definitions with fields, validators, enums
- `docs/design/13-project-structure.md` — Project layout, pyproject.toml, module responsibilities
- `docs/design/04-system-design.md` — Architecture, exception handling, sandbox policy, logging spec
- `docs/design/09-ai-handoff.md` — 8 fake implementations, mocking strategy, test layers
- `docs/design/14-cli-spec.md` — CLI subcommand specs (ddk init, ddk doctor/preflight)
- `docs/design/33-security-privacy-governance.md` — 7 redaction regex patterns, Pydantic field annotations
- `docs/design/03-constraints-nfr.md` — NFR targets, Ruff/Pyright config, timeout defaults
- `docs/design/05-adr-set.md` — 25 ADR decisions (DI, FakeLLM, logging, sandbox, etc.)
- `.planning/research/ARCHITECTURE.md` — LangGraph context_schema + Runtime[T] verification
- `.planning/research/PITFALLS.md` — 12 pitfalls with prevention strategies
- `.planning/research/STACK.md` — 10 runtime deps, version constraints, dependency analysis
- **LIVE VERIFICATION** — LangGraph 1.1.2 `context_schema` + `Runtime[T]` + `functools.partial` wrapper tested on Python 3.14 (this session)

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` — Overall project research summary and roadmap rationale

### Tertiary (LOW confidence)
- None — all Phase 1 patterns are well-documented in design docs and verified locally

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all versions verified against installed packages on this machine
- Architecture: HIGH — LangGraph DI pattern live-verified with working code
- Pitfalls: HIGH — derived from design doc analysis + local verification of Python 3.14 compat
- Models: HIGH — complete inventory from authoritative design doc (12-data-models.md)

**Research date:** 2025-07-27
**Valid until:** 2025-08-27 (stable patterns, no fast-moving APIs)

# Technology Stack

**Project:** ddalggak (딸깍) — Delivery Pipeline MVP
**Researched:** 2025-07-27
**Scope:** Additional libraries beyond the locked stack for 21 P0 requirements

## Context

The locked stack (Python 3.12+, uv, Typer, Pydantic v2, LangGraph, Playwright Python, scikit-image, Ruff+Pyright, pytest, git worktree) is NOT re-evaluated here. This document covers **only** the additional dependencies needed to implement the 21 P0 requirements.

---

## Recommended Stack

### LLM Client Libraries

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `anthropic` | `>=0.40.0` | Primary LLM provider (Claude) | Design docs specify direct SDK with `tool_use` for structured output. ADR-020 locks Anthropic as primary. AsyncAnthropic client used throughout. 8 direct dependencies — lightweight. **Confidence: HIGH** |
| `openai` | `>=1.40.0` | Fallback LLM provider | ADR-020 mandates fallback to GPT-4o. `AsyncOpenAI` with `response_format` for structured output. Design doc `11-llm-interface.md` has concrete implementation contracts using direct SDK. **Confidence: HIGH** |

**Decision: Direct SDKs, NOT LiteLLM.**

Rationale:
1. **Design docs already specify direct SDK usage.** `11-llm-interface.md` has concrete `AnthropicAdapter` and `OpenAIAdapter` implementations using `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI`. Switching to LiteLLM would invalidate 200+ lines of design contracts.
2. **Dependency weight.** LiteLLM pulls 12+ direct dependencies (including aiohttp, tiktoken, tokenizers, jinja2, jsonschema, click, openai). Anthropic SDK has only 8 deps. Together `anthropic` + `openai` are far lighter than `litellm` alone.
3. **Structured output patterns differ.** Anthropic uses `tool_use` blocks, OpenAI uses `response_format`. The design already encodes this in the `LLMAdapter` Protocol with per-provider `complete_structured()` — the exact abstraction LiteLLM would provide, but without the 50+ transitive deps.
4. **Cost tracking.** The design has a custom `CostTracker` with per-model token pricing tables. LiteLLM's cost tracking would be redundant and less controllable.
5. **Only 2 providers for P0.** LiteLLM's value is provider breadth (100+ models). P0 needs exactly 2 providers with full control over fallback logic (`LLMFallbackChain` in design).
6. **No version staleness risk.** Direct SDKs update same-day when providers ship new features. LiteLLM is always N days behind.

### Image Processing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pillow` | `>=10.0.0` | Image preprocessing for multimodal LLM intake | Design doc `11-llm-interface.md` explicitly uses `PIL.Image` for resize + base64 encoding. Images may exceed Anthropic's 5MB limit — Pillow handles LANCZOS downscaling. Also used in `12-data-models.md` ImagePreprocessor. Supports PNG/JPEG/WebP. Zero-dependency alternative doesn't exist for this use case. **Confidence: HIGH** |

**Note:** scikit-image (locked for SSIM) already depends on Pillow, so this adds zero new transitive deps.

### CLI Output & Formatting

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `rich` | `>=13.0.0` | Progress bars, live tables, formatted console output | `14-cli-spec.md` explicitly specifies "Rich progress bar + live table". `typer>=0.12.0` now includes `rich` as a **direct dependency** (verified: Typer 0.24.1 lists `rich>=12.3.0` in requires_dist). So `rich` is already transitively installed. Adding explicit version pin `>=13.0.0` ensures access to latest Console, Progress, Live, and Panel features. **Confidence: HIGH** |

**Note:** `typer[all]` extras syntax is no longer needed as of Typer 0.12+. Typer now depends on `rich` directly, not as an optional extra. Change `typer[all]>=0.12.0` to `typer>=0.15.0` in pyproject.toml to reflect this.

### Structured Logging

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `structlog` | `>=24.0.0` | Structured JSON logging with context binding | `14-cli-spec.md` names structlog for "JSON 모드 지원". BUT `33-security-privacy-governance.md` implements logging with **stdlib `logging`** using custom `RedactingFormatter` and `StructuredJSONFormatter`. **Recommendation: Use structlog as the wrapper around stdlib logging**, not as a replacement. structlog has zero runtime dependencies, integrates with stdlib handlers, and provides `bind()` for node/case_id context propagation through LangGraph nodes. This eliminates manual `record.extra` handling seen in the security doc. **Confidence: MEDIUM** |

**Integration pattern:**
```python
# structlog configures stdlib logging underneath
import structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        RedactingProcessor(),  # custom, replaces RedactingFormatter
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),  # replaces StructuredJSONFormatter
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
```

structlog's `bind(node="ingest", case_id="C-001")` is ideal for passing context through async LangGraph nodes without threading log context manually.

### Git Operations

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `gitpython` | `>=3.1.40` | Git adapter for worktree, checkpoint, rollback operations | Listed in `13-project-structure.md` pyproject.toml. Used by `adapters/git.py`, `workspace/checkpoint.py`, `workspace/rollback.py`. **However, the sandbox design (`15-sandbox-design.md`) uses raw `subprocess.run(["git", ...])` calls.** **Confidence: MEDIUM** |

**Decision: Include GitPython, but scope its usage carefully.**

Analysis of git operations in the design docs:

| Operation | Location | Current impl | GitPython value |
|-----------|----------|--------------|-----------------|
| `git worktree add` | sandbox/worktree.py | subprocess | Low — subprocess is fine |
| `git worktree remove` | sandbox/worktree.py | subprocess | Low |
| `git rev-parse HEAD` | sandbox/worktree.py | subprocess | Low |
| `git status --porcelain` | rollback SOP | subprocess | Medium — GitPython parses output |
| `git checkout / reset` | rollback controller | subprocess | Medium — error handling |
| `git stash` | rollback SOP | subprocess | Medium |
| `git clean -fd` | rollback SOP | subprocess | Low |
| `git diff --name-only` | evidence builder | subprocess | Medium — structured output |

**Recommendation:** Use GitPython for `adapters/git.py` (the central Git adapter) which provides:
- Parsed status output (not raw string parsing)
- Exception hierarchy for error handling
- Repo validation (is it a git repo?)
- Commit/ref resolution

Keep raw `subprocess` for hot-path sandbox operations (`worktree add/remove`) where GitPython adds overhead and the commands are simple. This hybrid approach matches what the sandbox design already does.

### HTTP Client (Async)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | `>=0.27.0` | Async HTTP for dev server health checks | Listed in `13-project-structure.md`. **BUT**: `20-playwright-adapter.md` uses `aiohttp` for boot detection HTTP checks. The `anthropic` SDK already depends on `httpx`. **Confidence: MEDIUM** |

**Decision: Use httpx, NOT aiohttp.**

Rationale:
1. `anthropic` SDK already pulls in `httpx` as a dependency — zero additional install.
2. `aiohttp` would be a new dependency (with C extensions, slower install on macOS ARM).
3. The boot detection code in `20-playwright-adapter.md` uses `aiohttp.ClientSession` — replace with `httpx.AsyncClient` (API is nearly identical).
4. `httpx` has a simpler API, better type hints, and works sync+async.

**Migration of design doc code:**
```python
# Before (aiohttp in 20-playwright-adapter.md):
async with aiohttp.ClientSession() as session:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
        if 200 <= resp.status < 300: ...

# After (httpx):
async with httpx.AsyncClient() as client:
    resp = await client.get(url, timeout=3.0)
    if resp.is_success: ...
```

### Async Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pytest-asyncio` | `>=0.23.0` | Async test support for LangGraph nodes | All LangGraph nodes are `async def`. Design pyproject.toml sets `asyncio_mode = "auto"`. Required for `async with WorktreeSandbox.create()` integration tests. **Confidence: HIGH** |
| `pytest-cov` | `>=5.0.0` | Coverage reporting | Listed in dev deps. Standard practice. **Confidence: HIGH** |
| `pytest-mock` | `>=3.14.0` | Mock fixtures for adapter testing | Listed in dev deps. Provides `mocker` fixture. **Confidence: HIGH** |

### Build System

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `hatchling` | `>=1.25.0` | PEP 517 build backend | Specified in `13-project-structure.md` pyproject.toml `[build-system]`. Lightweight, fast, well-maintained. **Confidence: HIGH** |

### MCP Server (Phase 5 scope but listed in pyproject.toml)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `mcp` | `>=1.0.0` | FastMCP server for AI tool integration | Listed in design pyproject.toml. `ddk mcp` command uses FastMCP. **BUT: MCP/multi-tool adapter is explicitly OUT OF SCOPE for v1.0 (DDK-REQ-025~029).** Do NOT include in P0 dependencies. Add when Phase 5 milestone begins. **Confidence: HIGH — confident it should be EXCLUDED from P0** |

---

## Stack NOT Needed (Avoid Bloat)

These were considered but should NOT be added:

| Library | Why Considered | Why NOT to Add |
|---------|---------------|----------------|
| `litellm` | Multi-provider LLM abstraction | P0 needs only 2 providers. Design already has `LLMAdapter` Protocol + per-provider implementations. LiteLLM adds 12+ deps including tiktoken, tokenizers (heavy). See detailed analysis above. |
| `aiohttp` | Used in design doc for HTTP health checks | `httpx` already transitively installed via `anthropic`. Replace the 3 lines of aiohttp in boot detection. Avoids C extension compilation. |
| `mcp` | MCP server listed in pyproject.toml | Out of scope for v1.0 milestone. DDK-REQ-025~029 deferred to Phase 5. |
| `tenacity` | Retry logic library | Design has custom `LLMRetryPolicy` with exponential backoff+jitter (10 lines). Adding tenacity for this would be over-engineering. The retry logic is LLM-specific with provider fallback — not generic. |
| `loguru` | Alternative structured logging | structlog is named in CLI spec. loguru doesn't integrate with stdlib logging handlers (RedactingFormatter pattern). |
| `click` | CLI framework | Already transitively installed by Typer. Never import directly — use Typer's API. |
| `numpy` | Array operations for SSIM | Already transitively installed by scikit-image. Never import directly for P0 — only scikit-image's `structural_similarity` is needed. |
| `pydantic-settings` | Settings management from env vars | Overkill for P0. The config is a simple JSON file (`.ddk/config.json`) + env vars read via `os.environ`. Add later if config grows complex. |
| `anyio` | Async abstraction layer | Already transitively installed by `anthropic` SDK. Not needed directly — use `asyncio` stdlib. |
| `tiktoken` / `tokenizers` | Token counting | P0 cost tracking uses simple `input_tokens`/`output_tokens` from API response (already returned by both SDKs). Pre-call token estimation is not a P0 requirement. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| LLM Client | anthropic + openai (direct) | litellm | 12+ heavy deps, only 2 providers needed, design contracts specify direct SDK |
| HTTP Client | httpx (transitive via anthropic) | aiohttp | Adds C extension dep, anthropic already brings httpx |
| Logging | structlog + stdlib | loguru | loguru can't wrap stdlib handlers; structlog can |
| Logging | structlog + stdlib | stdlib only | Possible but requires manual context binding; structlog's `bind()` is ideal for per-node context in LangGraph |
| Git Operations | gitpython + subprocess hybrid | subprocess only | Subprocess-only works but requires manual output parsing for status/diff; GitPython provides parsed objects |
| Git Operations | gitpython + subprocess hybrid | gitpython only | GitPython adds overhead for simple worktree add/remove; subprocess is faster for hot-path sandbox ops |
| CLI Output | rich (via typer) | click.echo | Rich already installed; provides progress bars, tables, panels that CLI spec requires |
| Retry Logic | Custom LLMRetryPolicy | tenacity | Design already specifies custom retry with provider fallback chain; tenacity doesn't model provider switching |
| Build Backend | hatchling | setuptools / flit | hatchling specified in design; lightweight, fast |

---

## Final pyproject.toml Dependencies (P0)

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
    # CLI framework (brings rich transitively)
    "typer>=0.15.0",
    
    # Data validation (40+ models defined)
    "pydantic>=2.7.0",
    
    # Orchestration state machine
    "langgraph>=0.2.0",
    
    # LLM providers — direct SDKs (ADR-020)
    "anthropic>=0.40.0",
    "openai>=1.40.0",
    
    # Browser automation — screenshots + console capture
    "playwright>=1.44.0",
    
    # Image processing — multimodal intake resize/encode
    "pillow>=10.4.0",
    
    # Visual regression — SSIM comparison
    "scikit-image>=0.22.0",
    
    # Git operations — repo adapter (checkpoint, rollback, diff)
    "gitpython>=3.1.40",
    
    # Structured logging — JSON mode + context binding
    "structlog>=24.0.0",
    
    # httpx NOT listed — already transitive via anthropic SDK
    # rich NOT listed — already transitive via typer
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

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "UP", "B", "C4", "SIM"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
```

### Changes from Design Doc pyproject.toml

| Design Doc Version | Recommended Change | Reason |
|--------------------|--------------------|--------|
| `typer[all]>=0.12.0` | `typer>=0.15.0` | `[all]` extra no longer exists; rich is a direct dep since 0.12 |
| `rich>=13.0.0` | REMOVED (explicit) | Transitive via typer; no need to pin separately |
| `httpx>=0.27.0` | REMOVED (explicit) | Transitive via anthropic SDK; no direct import needed |
| `mcp>=1.0.0` | REMOVED | Out of scope for v1.0 milestone |
| `ruff>=0.7.0` | Moved to `[dev]` | Not a runtime dependency |
| `pyright>=1.1.380` | Moved to `[dev]` | Not a runtime dependency |

---

## Dependency Graph (P0 Runtime)

```
ddalggak
├── typer ─── rich (CLI output)
│             └── click
├── pydantic
├── langgraph ─── langchain-core
├── anthropic ─── httpx (async HTTP, also for boot detection)
│                 ├── anyio
│                 └── pydantic
├── openai ─── httpx
│              └── pydantic  
├── playwright (browser automation)
├── pillow (image processing)
├── scikit-image ─── numpy
│                    └── pillow
├── gitpython ─── gitdb
└── structlog (zero runtime deps)
```

**Total direct dependencies: 10**
**Key transitive deps reused: httpx (from anthropic), rich (from typer), pillow (from scikit-image)**

---

## Async Patterns for LangGraph Nodes

All LangGraph nodes are `async def` per the design. Key patterns:

1. **Node functions** return `dict` partial state updates (LangGraph convention)
2. **LLM calls** use `await adapter.complete_structured(...)` — both SDKs provide async clients
3. **Subprocess calls** use `asyncio.create_subprocess_exec()` for sandbox commands (not `subprocess.run`)
4. **Playwright** uses `async_playwright()` context manager
5. **httpx** uses `httpx.AsyncClient()` for dev server boot detection

No additional async library is needed. Python 3.12+ stdlib `asyncio` handles everything. LangGraph's `StateGraph.compile()` produces a graph that runs nodes via `await`.

---

## Cost Tracking Architecture

Design doc `11-llm-interface.md` specifies a **custom `CostTracker`** class with:
- Per-model token pricing tables (hardcoded, updated per model release)
- Per-case cost cap (env var `DDK_LLM_COST_CAP_USD`, default $2.00)
- `CostCapExceededError` exception for graceful shutdown

This requires **zero additional libraries**. Token counts come from LLM API responses (`input_tokens`, `output_tokens`). Cost = `tokens * price_per_1k / 1000`. The implementation is ~30 lines of pure Python.

---

## Installation

```bash
# Core project setup
uv init
uv add typer pydantic langgraph anthropic openai playwright pillow scikit-image gitpython structlog

# Dev dependencies
uv add --dev pytest pytest-asyncio pytest-cov pytest-mock ruff pyright

# Playwright browser (one-time setup)
uv run playwright install chromium
```

---

## Integration Points with Locked Stack

| Locked Tech | Integration With New Libs | Notes |
|-------------|--------------------------|-------|
| **Pydantic v2** | anthropic `tool_use` schema → `model.model_json_schema()` | Direct integration for structured LLM output |
| **Pydantic v2** | openai `response_format` → Pydantic model class | OpenAI SDK natively accepts Pydantic models |
| **LangGraph** | All async nodes → anthropic/openai async clients | `async def node(state) -> dict` pattern |
| **LangGraph** | structlog `bind()` for per-node logging context | `log = log.bind(node="ingest", case_id=state["case_id"])` |
| **Typer** | rich Console/Progress/Live for CLI output | Typer already depends on rich — import directly |
| **Playwright** | httpx (via anthropic) for boot detection health checks | Replace aiohttp usage in design doc |
| **scikit-image** | Pillow for image loading before SSIM | scikit-image already depends on Pillow |
| **git worktree** | GitPython for high-level ops, subprocess for worktree commands | Hybrid approach per operation type |
| **pytest** | pytest-asyncio for async node tests | `asyncio_mode = "auto"` in pyproject.toml |

---

## Version Currency Check

All versions verified against PyPI on 2025-07-27:

| Package | Minimum Spec | Latest on PyPI | Status |
|---------|-------------|----------------|--------|
| anthropic | >=0.40.0 | 0.86.0 | ✅ Current |
| openai | >=1.40.0 | 2.30.0 | ✅ Current (note: major version jump to 2.x) |
| pillow | >=10.4.0 | 12.1.1 | ✅ Current |
| gitpython | >=3.1.40 | 3.1.46 | ✅ Current |
| structlog | >=24.0.0 | 25.5.0 | ✅ Current |
| typer | >=0.15.0 | 0.24.1 | ✅ Current |
| langgraph | >=0.2.0 | 1.1.3 | ✅ Current |
| pydantic | >=2.7.0 | 2.12.5 | ✅ Current |
| playwright | >=1.44.0 | 1.58.0 | ✅ Current |
| scikit-image | >=0.22.0 | 0.26.0 | ✅ Current |
| pytest-asyncio | >=0.23.0 | 1.3.0 | ✅ Current |
| hatchling | >=1.25.0 | 1.29.0 | ✅ Current |
| ruff | >=0.5.0 | 0.15.8 | ✅ Current |
| pyright | >=1.1.380 | 1.1.408 | ✅ Current |

**⚠️ OpenAI SDK version note:** The design doc specifies `openai>=1.40.0` but the latest is `2.30.0` (major version bump). The `beta.chat.completions.parse()` API used in the design doc's `OpenAIAdapter` may have moved to stable in v2. Verify the structured output API path during implementation. Pin to `>=1.40.0` for now — both v1 and v2 should work.

---

## Sources

- `docs/design/11-llm-interface.md` — LLM adapter contracts, provider decision (ADR-020) — **PRIMARY**
- `docs/design/13-project-structure.md` — pyproject.toml, dependency list — **PRIMARY**
- `docs/design/14-cli-spec.md` — CLI tech choices (Rich, structlog) — **PRIMARY**
- `docs/design/15-sandbox-design.md` — Sandbox subprocess patterns — **PRIMARY**
- `docs/design/20-playwright-adapter.md` — aiohttp usage for boot detection — **PRIMARY**
- `docs/design/33-security-privacy-governance.md` — Logging implementation with stdlib — **PRIMARY**
- PyPI package metadata — Version verification — **HIGH confidence**
- Typer 0.24.1 requires_dist — rich dependency verification — **HIGH confidence**
- Anthropic SDK 0.86.0 requires_dist — httpx transitive dep verification — **HIGH confidence**
- LiteLLM 1.82.6 requires_dist — Dependency weight comparison — **HIGH confidence**

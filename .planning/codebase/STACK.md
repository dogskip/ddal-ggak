# Technology Stack

**Analysis Date:** 2026-07-27

## Languages

**Primary:**
- Python 3.12+ - Core application language and MCP server runtime
  - Strict type checking with Pyright (strict mode)
  - Used throughout `src/ddk/`

## Runtime

**Environment:**
- Python 3.12 (minimum required per `pyproject.toml`)
- CPython-compatible (platform-specific Playwright wheels available)

**Package Manager:**
- uv (Astral) - Fast package manager with lock file support
- Lockfile: `uv.lock` (present, pinned versions)

## Frameworks

**Core Application:**
- LangGraph 1.2.9 - Agentic workflow orchestration
  - State graph construction at `src/ddk/graph/builder.py`
  - Node-based pipeline execution (intake → design → generate → validate → certify)
  - Checkpointing via `langgraph-checkpoint` 4.1.1
  - Prebuilt components via `langgraph-prebuilt` 1.1.0

**CLI:**
- Typer 0.27.0 - CLI framework (async-friendly)
  - Entry point: `src/ddk/cli/` (package), also `python -m ddk`
  - Registered as `ddk` command in `pyproject.toml` scripts

**MCP Server:**
- MCP (Model Context Protocol) 1.28.1 - FastMCP-based server
  - Server implementation: `src/ddk/server.py`
  - Stdio transport for IDE integration (Claude, OpenCode, Gemini)
  - Exposes tools: `design_new()`, `preflight()`, `ddk_version()`

**LLM Integration:**
- Anthropic SDK 0.120.0 - Claude API client
  - Async support (AsyncAnthropic)
  - Default routing: Claude Sonnet 4.6 / Haiku 4.5
  - Adapter: `src/ddk/adapters/llm/claude.py`

**Data Validation:**
- Pydantic 2.13.4 - Schema validation and serialization
  - Configuration management via `pydantic-settings` 2.14.2
  - BaseSettings pattern at `src/ddk/models/config.py`

**Logging:**
- structlog 25.5.0 - Structured logging with filtering
  - Secret redaction processor at `src/ddk/logging/setup.py`
  - JSON and text formatters available

**Testing:**
- pytest 9.1.1 - Test runner
- pytest-asyncio 0.23+ - Async test support
- pytest-cov 5.0+ - Coverage reporting
- pytest-mock 3.14+ - Mock/patch utilities
- pytest-playwright 0.5+ - Playwright integration testing

**Code Quality:**
- Ruff 0.16.0 - Linter (E, F, I, N, UP, B, C4, SIM rules)
- Pyright 1.1.411 - Type checker (strict mode)
- ESC (formatter configured but not explicitly referenced)

## Key Dependencies

**Critical:**
- `anthropic` 0.120.0 - LLM provider; blocks if `DDK_ANTHROPIC_API_KEY` unset
- `langgraph` 1.2.9 - Workflow engine; core to design pipeline
- `mcp` 1.28.1 - IDE integration protocol

**Infrastructure & Protocol:**
- `gitpython` 3.1.57 - Git repository read operations (worktree management via subprocess per D-04)
- `playwright` 1.61.0 - Optional browser test dependency; production adapter not wired
- `pillow` 12.3.0 - Image processing for screenshot comparison (SSIM-based diffing)

**HTTP & Networking:**
- `httpx` - HTTP client (dep of anthropic SDK)
- `anyio` 4.14.2 - Async I/O abstraction layer

**Utilities:**
- `typer` 0.27.0 - CLI argument parsing
- `rich` 13.9.4 - Terminal output formatting and progress indicators
- `structlog` 25.5.0 - Structured logging with secret redaction

**Type Support:**
- `pydantic` 2.13.4 - Data validation
- `pydantic-settings` 2.14.2 - Environment-based configuration
- `typing-extensions` - Backward-compatible type hints

## Configuration

**Environment Configuration:**
- Pydantic BaseSettings with `env_prefix = "DDK_"`
- `.env` file support (loaded via `pydantic-settings`)
- Configuration file: `src/ddk/models/config.py`

**Key Environment Variables:**
- `DDK_ANTHROPIC_API_KEY` - Anthropic API key (required for LLM operations)
- `DDK_OPENAI_API_KEY` - OpenAI API key (optional, future support)
- `DDK_LLM_PROVIDER` - Runtime provider (`anthropic`; other enum values are reserved)
- `DDK_LLM_MODEL` - Default LLM model (default: `claude-sonnet-4-6`)
- `DDK_LIGHT_MODEL` - Lightweight model (default: `claude-haiku-4-5-20251001`)
- `DDK_COST_CAP_USD` - Cost limit per operation (default: 2.0)
- `DDK_SANDBOX_MODE` - Implemented sandbox type (`tempdir`; other values fail preflight)
- `DDK_SANDBOX_TIMEOUT_SECONDS` - Command execution timeout (default: 300)
- `DDK_PLAYWRIGHT_BROWSER` - Browser type ("chromium" | "firefox" | "webkit")
- `DDK_LOG_LEVEL` - Log level (default: "INFO")
- `DDK_LOG_FORMAT` - Log format ("text" | "json")
- `DDK_LOG_REDACT` - Enable secret redaction in logs (default: True)
- `DDK_CASE_DIR` - Workspace directory (default: ".ddk")
- `DDK_SSIM_THRESHOLD` - Image similarity threshold (default: 0.92)
- `DDK_PIXEL_DIFF_THRESHOLD` - Pixel difference tolerance (default: 0.05)

**Linting Configuration:**
- Ruff config at `pyproject.toml`: target Python 3.12, line length 100
- Pyright config at `pyproject.toml`: strict type checking, venv at `.venv`

**Build Configuration:**
- Hatchling build backend
- Wheel package includes: `src/ddk/` → `ddk/` + assets from `src/ddk/assets/`
- CLI entry point: `ddk = "ddk.cli:app"`

## Platform Requirements

**Development:**
- Python 3.12+
- Git (for repository operations)
- Playwright browser binaries (chromium/firefox/webkit)
- 2GB+ RAM (for LLM inference and browser automation)

**Production/MCP Server:**
- Python 3.12+ runtime
- Anthropic API key (for Claude integration)
- Network access to `https://api.anthropic.com` (port 443)
- Stdio transport (piped input/output for IDE integration)
- Optional: Git repository and Playwright for local testing workflows

**Optional Dependencies:**
- `pytest-playwright` - Only needed for visual regression testing
- Gemini CLI - For Gemini tool integration
- OpenCode IDE - For OpenCode MCP server registration
- Claude Code - For Claude MCP server registration

---

*Stack analysis: [2026-07-27]*

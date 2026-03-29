# Technology Stack

**Analysis Date:** 2025-03-29

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
- LangGraph 1.1.3 - Agentic workflow orchestration
  - State graph construction at `src/ddk/graph/builder.py`
  - Node-based pipeline execution (intake → design → generate → validate → certify)
  - Checkpointing via `langgraph-checkpoint` 4.0.1
  - Prebuilt components via `langgraph-prebuilt` 1.0.8

**CLI:**
- Typer 0.24.1 - CLI framework (async-friendly)
  - Entry point: `src/ddk/cli.py`
  - Registered as `ddk` command in `pyproject.toml` scripts

**MCP Server:**
- MCP (Model Context Protocol) 1.26.0 - FastMCP-based server
  - Server implementation: `src/ddk/server.py`
  - Stdio transport for IDE integration (Claude, OpenCode, Gemini)
  - Exposes tools: `design_new()`, `preflight()`, `ddk_version()`

**LLM Integration:**
- Anthropic SDK 0.86.0 - Claude API client
  - Async support (AsyncAnthropic)
  - Claude 3.5 Sonnet / Haiku models supported
  - Adapter: `src/ddk/adapters/llm/claude.py`

**Data Validation:**
- Pydantic 2.12.5 - Schema validation and serialization
  - Configuration management via `pydantic-settings` 2.13.1
  - BaseSettings pattern at `src/ddk/models/config.py`

**Logging:**
- structlog 25.5.0 - Structured logging with filtering
  - Secret redaction processor at `src/ddk/logging/setup.py`
  - JSON and text formatters available

**Testing:**
- pytest 8.0+ - Test runner
- pytest-asyncio 0.23+ - Async test support
- pytest-cov 5.0+ - Coverage reporting
- pytest-mock 3.14+ - Mock/patch utilities
- pytest-playwright 0.5+ - Playwright integration testing

**Code Quality:**
- Ruff 0.5+ - Linter (E, F, I, N, UP, B, C4, SIM rules)
- Pyright 1.1.380+ - Type checker (strict mode)
- ESC (formatter configured but not explicitly referenced)

## Key Dependencies

**Critical:**
- `anthropic` 0.86.0 - LLM provider; blocks if `DDK_ANTHROPIC_API_KEY` unset
- `langgraph` 1.1.3 - Workflow engine; core to design pipeline
- `mcp` 1.26.0 - IDE integration protocol; enables Claude/OpenCode/Gemini integrations

**Infrastructure & Protocol:**
- `gitpython` 3.1.46 - Git repository read operations (worktree management via subprocess per D-04)
- `playwright` 1.58.0 - Browser automation for screenshot diffing and visual validation
- `pillow` 12.1.1 - Image processing for screenshot comparison (SSIM-based diffing)

**HTTP & Networking:**
- `httpx` - HTTP client (dep of anthropic SDK)
- `anyio` 4.13.0 - Async I/O abstraction layer

**Utilities:**
- `typer` 0.24.1 - CLI argument parsing
- `rich` 14.3.3 - Terminal output formatting and progress indicators
- `structlog` 25.5.0 - Structured logging with secret redaction

**Type Support:**
- `pydantic` 2.12.5 - Data validation
- `pydantic-settings` 2.13.1 - Environment-based configuration
- `typing-extensions` - Backward-compatible type hints

## Configuration

**Environment Configuration:**
- Pydantic BaseSettings with `env_prefix = "DDK_"`
- `.env` file support (loaded via `pydantic-settings`)
- Configuration file: `src/ddk/models/config.py`

**Key Environment Variables:**
- `DDK_ANTHROPIC_API_KEY` - Anthropic API key (required for LLM operations)
- `DDK_OPENAI_API_KEY` - OpenAI API key (optional, future support)
- `DDK_LLM_PROVIDER` - LLM provider selection ("anthropic" | "openai" | "fake")
- `DDK_LLM_MODEL` - Default LLM model (default: "claude-3-5-sonnet-20241022")
- `DDK_LIGHT_MODEL` - Lightweight model for simple tasks
- `DDK_COST_CAP_USD` - Cost limit per operation (default: 2.0)
- `DDK_SANDBOX_MODE` - Sandbox type ("worktree" | "tempdir")
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

*Stack analysis: [2025-03-29]*

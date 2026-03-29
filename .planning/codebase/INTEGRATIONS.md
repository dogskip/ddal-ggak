# External Integrations

**Analysis Date:** 2025-03-29

## APIs & External Services

**Large Language Models:**
- Anthropic Claude API - Primary LLM provider for design generation and validation
  - SDK/Client: `anthropic` 0.86.0
  - Auth: `DDK_ANTHROPIC_API_KEY` (environment variable)
  - Implementation: `src/ddk/adapters/llm/claude.py`
  - Models: Claude 3.5 Sonnet (default), Claude 3 Haiku (light model), Claude 3 Opus (optional)
  - Cost tracking: Per-token pricing with `DDK_COST_CAP_USD` limit

- OpenAI API - Secondary LLM provider (stub support)
  - SDK/Client: Not yet integrated (placeholder in `src/ddk/models/config.py`)
  - Auth: `DDK_OPENAI_API_KEY` (environment variable, currently unused)
  - Status: Configuration only, no active adapter yet

## Data Storage

**Databases:**
- None - Stateless design (no persistent database)
- Workspace data: Filesystem-based, stored in `.ddk/` directory by default
- State checkpointing: LangGraph checkpoints via `langgraph-checkpoint` (in-memory or filesystem)

**File Storage:**
- Local filesystem only - No cloud storage integration
  - Workspace root: Configurable via `DDK_CASE_DIR` (default: `.ddk`)
  - Design packages: Written to `design-package/` subdirectory
  - Test artifacts: Stored alongside code under `.ddk/`
  - Screenshot diffs: Cached in workspace

**Caching:**
- None - No dedicated cache provider
- LangGraph state management handles invocation deduplication
- Playwright browser instances cached within session

## Authentication & Identity

**Auth Provider:**
- Custom - API key based
  - Implementation: `src/ddk/models/config.py` (Pydantic BaseSettings)
  - Anthropic: Bearer token auth via HTTP headers (handled by SDK)
  - No user identity/session management (service-to-service auth only)
  - Secrets redaction: `src/ddk/security/redact.py` (regex-based masking)

**Secrets Management:**
- Environment variables: Primary method
  - `.env` file support via `pydantic-settings`
  - Redaction patterns for API keys (OpenAI `sk-`, Anthropic `sk-ant-`, etc.)
  - Log filtering: `DDK_LOG_REDACT=true` enables automatic masking
  - Redaction patterns defined in `src/ddk/security/redact.py`

## Monitoring & Observability

**Error Tracking:**
- None detected - Application logs to stdout/stderr only

**Logs:**
- Structured logging via `structlog` 25.5.0
  - Configuration: `src/ddk/logging/setup.py`
  - Format: JSON or text (configurable via `DDK_LOG_FORMAT`)
  - Output: Console (stdout/stderr)
  - Secret redaction: Automatic when `DDK_LOG_REDACT=true`
  - Log levels: Configurable via `DDK_LOG_LEVEL` (default: INFO)

**Cost Tracking:**
- Per-call token usage and estimated USD cost
  - Implemented in `src/ddk/adapters/llm/claude.py` (cost calculation)
  - Tracks input/output tokens and applies per-model pricing
  - Enforced via `DDK_COST_CAP_USD` limit (default: $2.00)

## CI/CD & Deployment

**Hosting:**
- IDE-embedded MCP server (Claude, OpenCode, Gemini)
- Localhost CLI tool (Python package)
- No cloud hosting / deployment platform integration

**CI Pipeline:**
- None detected in codebase
- Test framework present: pytest with asyncio support

## Environment Configuration

**Required Env Vars:**
- `DDK_ANTHROPIC_API_KEY` - **Critical** for LLM operations
  - Format: `sk-ant-[alphanumeric-hyphens]{20,}`
  - Obtained from: https://console.anthropic.com/

**Secrets Location:**
- Environment variables (OS-specific)
- Optional `.env` file (loaded by pydantic-settings)
- **SECURITY**: Never commit `.env` or secrets to Git

**Optional Configuration:**
- `DDK_OPENAI_API_KEY` - For future OpenAI integration
- `DDK_LLM_PROVIDER` - Switch between providers
- `DDK_LLM_MODEL` - Default model selection
- `DDK_SANDBOX_MODE` - Sandbox isolation strategy
- `DDK_PLAYWRIGHT_BROWSER` - Browser selection for visual tests
- `DDK_LOG_LEVEL`, `DDK_LOG_FORMAT` - Logging tuning

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Tool Integrations

**IDE/Editor Integration (MCP Protocol):**
- Claude Code
  - Type: MCP server via stdio
  - Config location: `.claude/settings.json`
  - Commands registered to: `.claude/commands/ddk/`
  - Installation: `ddk install claude`

- OpenCode
  - Type: MCP server via stdio
  - Config location: `.opencode/config.json`
  - Commands registered to: `.opencode/commands/ddk/`
  - Installation: `ddk install opencode`

- Gemini CLI
  - Type: Slash command registration
  - Config location: `.gemini/commands/ddk/`
  - Installation: `ddk install gemini`

- Cursor/Copilot/Kiro/Codex
  - Type: Slash command bundles
  - Installed via asset directories in `src/ddk/assets/commands/`
  - Installation: `ddk install <tool-name>`

**MCP Server Details:**
- Transport: stdio (piped input/output)
- Tools exposed:
  - `design_new(idea, output_dir, non_interactive)` - Generate design documents
  - `preflight()` - Check environment readiness
  - `ddk_version()` - Get version info
- Implementation: `src/ddk/server.py` (FastMCP-based)

## Version Control Integration

**Git Operations:**
- Read operations: GitPython (`gitpython` 3.1.46)
  - Status, diff, log queries
  - Implementation: `src/ddk/adapters/local_git.py`

- Write operations: subprocess + git CLI
  - Worktree creation/removal
  - Checkpoint creation
  - Rollback operations
  - Rationale (per D-04): Subprocess isolation for safety

- Git adapter protocol: `src/ddk/adapters/git.py`
  - Async interface for write operations
  - Synchronous interface for read operations

**Sandbox Strategies:**
- **Worktree mode** (default): Git worktree isolation per `DDK_SANDBOX_MODE=worktree`
  - Safe branching without checkout conflicts
  - Timeout: `DDK_SANDBOX_TIMEOUT_SECONDS` (default: 300s)

- **Tempdir mode**: Temporary directory copy
  - Fallback when git unavailable
  - Configuration: `DDK_SANDBOX_MODE=tempdir`

## Browser Automation

**Playwright Integration:**
- Package: `playwright` 1.58.0
- Purpose: Screenshot capture, visual regression testing, console error detection
- Adapter: `src/ddk/adapters/playwright_browser.py`
- Browser selection: `DDK_PLAYWRIGHT_BROWSER` (chromium/firefox/webkit)
- Features:
  - Viewport-based screenshot capture (default: 1280x800)
  - Browser console log capture (log/warn/error levels)
  - Network failure detection
  - Failed request correlation IDs

**Null Adapter** (for testing):
- `src/ddk/adapters/null_playwright.py` - No-op implementation for unit tests

## Screenshot Diffing

**Image Processing:**
- Pillow 12.1.1 - Image I/O and preprocessing
- SSIM (Structural Similarity) index-based diffing
- Configuration:
  - `DDK_SSIM_THRESHOLD` - Similarity tolerance (default: 0.92 = 92% match required)
  - `DDK_PIXEL_DIFF_THRESHOLD` - Pixel change tolerance (default: 0.05 = 5% changed pixels)

**Implementations:**
- `src/ddk/adapters/screenshot_diff.py` - Full diffing with Playwright
- `src/ddk/adapters/screenshot_diff_local.py` - Local file comparison only

---

*Integration audit: [2025-03-29]*

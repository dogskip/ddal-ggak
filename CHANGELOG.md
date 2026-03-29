# Changelog

All notable changes to ddalggak (ddk) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2025

### Added

#### Phase 1 — Core Infrastructure
- `DdalggakConfig` — pydantic-settings configuration with `.env` support
- `WorkspaceManager` — `.ddk/` workspace initialisation and case-storage
- Structured `CaseInput` / `GraphState` domain models
- `ddk init` — initialise `.ddk/` workspace in any directory
- `ddk version` — print installed package version

#### Phase 2 — LangGraph Pipeline (10-node)
- End-to-end delivery pipeline:
  `intake → intent_extract → design_system → plan → repo_scan → generate → normalize → validate → autofix → certify`
- LangGraph `StateGraph` builder with conditional routing
- `NodeWrapper` — uniform error handling and retries for every node
- `FakeLLMAdapter` and `TempDirSandbox` for deterministic offline testing

#### Phase 3 — Adapters & Services
- `FilesystemAdapter` — file read/write with path validation
- `GitAdapter` — `git add / commit / checkout` subprocess wrapper
- `LLMAdapter` — Anthropic Claude integration with cost tracking
- `PlaywrightAdapter` — headless screenshot capture (opt-in, `chromium` default)
- `ScreenshotDiffAdapter` — Pillow-only SSIM visual comparison
- `SandboxAdapter` — git-worktree isolation for generated code
- `SecurityRedactor` — strips secrets from log output
- 18 domain services (intent, design, planning, code-gen, linting, etc.)

#### Phase 4 — Failure Intelligence
- `FailureClassifier` — 11-taxonomy failure code system (FT-BUILD, FT-TYPE, FT-LINT, FT-RUNTIME, FT-VISUAL, FT-ASYNC, FT-UNKNOWN)
- `RollbackController` — git checkpoint creation and named-ref rollback
- `ddk rollback` CLI command

#### Phase 5 — Certification & Delivery
- `EvidencePack` — structured per-case evidence bundle
- `Scorecard` — weighted quality scoring (0–100)
- `ReleaseDecision` — PASS / CONDITIONAL_PASS / FAIL gate
- `ddk run` — full pipeline execution from CLI
- `ddk status` — case state and scorecard summary
- `ddk certify` — evidence and scorecard retrieval
- `ddk preflight` — environment pre-check (Python, API key, anthropic SDK)
- `ddk doctor` — full environment diagnosis (Python, uv, API key, Node.js, git)
- MCP server (`ddk serve`) — FastMCP stdio server exposing all pipeline tools
- `ddk install` — registers ddk as an AI tool in Claude Desktop / Cursor

### Changed
- `anthropic_api_key` now accepts both `DDK_ANTHROPIC_API_KEY` and plain `ANTHROPIC_API_KEY` (fallback); same for `openai_api_key` / `OPENAI_API_KEY`
- `ddk preflight` API-key label changed from `DDK_ANTHROPIC_API_KEY` to `LLM API key`

### Notes
- Requires Python ≥ 3.12
- Visual diff uses Pillow only (scikit-image removed)
- Playwright tests are opt-in (`-m playwright`)
- All 494 unit and integration tests pass under Python 3.14

[1.0.0]: https://github.com/bjchoi/ddalggak/releases/tag/v1.0.0

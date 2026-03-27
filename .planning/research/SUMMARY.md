# Project Research Summary

**Project:** ddalggak (딸깍) — Design-to-Delivery CLI Pipeline
**Domain:** AI-powered design-to-code generation with closed-loop validation
**Researched:** 2025-07-27
**Confidence:** HIGH

## Executive Summary

ddalggak is a Python CLI tool that takes design mockups (images + prompts) and produces buildable React/TypeScript code through a 10-node LangGraph pipeline: ingest → analyze → generate → validate → auto-fix → certify. This is a well-defined but novel product category — no existing tool implements the full closed-loop pipeline with automated visual regression, deterministic rule-based auto-fix, and evidence-gated release decisions. The closest competitors (Aider for lint auto-fix, Same.dev for bounded linter loops, screenshot-to-code for image-to-HTML) each solve one slice. ddalggak's differentiation is the integration of all slices into a single, auditable pipeline with zero external infrastructure requirements (git worktree sandbox, no Docker).

The recommended approach is a strict bottom-up build following the architecture's 4-layer dependency chain: pure Pydantic models → Protocol-based adapters → domain services → thin LangGraph nodes. The critical architectural decision — LangGraph's `context_schema` for dependency injection (verified against v1.1.3) — enables testability from day 1 by injecting `FakeLLM` and `InMemoryFilesystem` through a typed `ServiceContainer`. The stack is lean: 10 direct runtime dependencies, with heavy reuse of transitive deps (httpx via anthropic, rich via typer, pillow via scikit-image). Direct Anthropic + OpenAI SDKs over LiteLLM saves 12+ dependencies while matching the design docs' already-specified adapter contracts.

The top risks are: (1) **SSIM threshold calibration** — the single highest-risk feature, sensitive to viewport/font rendering/OS differences, requiring empirical calibration with fixture screenshots before any auto-fix visual rules work; (2) **LangGraph state mutation corruption** — nodes must never mutate mutable fields in-place, requiring strict conventions and contract tests from Phase 0; (3) **LLM cost runaway** during auto-fix retry loops — the $0.10/case budget is tight with 4+ LLM calls and up to 3 fix retries, requiring pre-call cost estimation and hard cost gates; (4) **Subprocess/browser process leaks** — Playwright Chromium zombies and orphaned dev servers after Ctrl+C require process group management (`os.setsid` + `os.killpg`) from the start.

## Key Findings

### Recommended Stack

The locked stack (Python 3.12+, uv, Typer, Pydantic v2, LangGraph, Playwright, scikit-image, Ruff+Pyright, pytest, git worktree) is set. Research identified 10 additional direct runtime dependencies needed for P0, with a strong bias toward minimal dependency weight and design doc alignment.

**Core technologies (additions to locked stack):**
- **anthropic SDK** (>=0.40.0): Primary LLM provider — direct SDK matches design contracts, avoids LiteLLM's 12+ deps
- **openai SDK** (>=1.40.0): Fallback LLM provider — ADR-020 mandates fallback to GPT-4o
- **Pillow** (>=10.4.0): Image preprocessing for multimodal LLM intake — zero new deps (scikit-image already depends on it)
- **structlog** (>=24.0.0): Structured logging with `bind()` for per-node context — zero runtime deps, bridges stdlib handlers
- **GitPython** (>=3.1.40): Git adapter for high-level ops — hybrid with subprocess for hot-path worktree commands
- **hatchling** (>=1.25.0): PEP 517 build backend — specified in design docs

**Key "NOT to add" decisions:**
- **LiteLLM**: Only 2 providers needed, design already specifies per-provider adapters, saves 12+ deps
- **aiohttp**: httpx already transitive via anthropic SDK, simpler API, no C extensions
- **tenacity**: Custom `LLMRetryPolicy` with provider fallback is only ~10 lines, tenacity can't model provider switching
- **mcp**: Out of scope for v1.0 (Phase 5 / Milestone v3.0)

**⚠️ Version alert:** OpenAI SDK jumped to v2.x — the `beta.chat.completions.parse()` API path may have changed. Verify during LLM adapter implementation.

### Expected Features

21 P0 requirements forming a complete delivery pipeline. Research confirms this feature set is unique in the market — no competitor implements all of: automated visual regression + deterministic auto-fix + evidence-gated release + git worktree sandbox.

**Must have (table stakes):**
- Screenshot/image + prompt intake (DDK-REQ-001, 002) — every competitor supports this
- React/TypeScript code generation (DDK-REQ-007) — market consensus target stack
- Buildable, type-safe, lint-clean output (DDK-REQ-009) — baseline expectation
- Repo convention awareness (DDK-REQ-003) — what separates from screenshot-to-code
- CLI interface with preflight doctor (DDK-REQ-021) — validates environment before run

**Should have (differentiators):**
- Automated SSIM visual regression (DDK-REQ-011) — **no competitor does this automatically**
- Deterministic rule-based auto-fix, not LLM re-prompting (DDK-REQ-012, 013) — architecturally distinct
- Evidence pack with full audit trail (DDK-REQ-014) — unique to ddalggak
- Git worktree sandbox isolation (DDK-REQ-009, 016) — zero-dependency, sub-second init
- Release decision gate with structured escalation (DDK-REQ-018) — no competitor has this

**Defer (v2+):**
- Design Studio (DDK-REQ-022-024) — separate product category, Phase 4
- MCP/Multi-tool adapter (DDK-REQ-025-029) — Phase 5
- Web UI / live preview — CLI-first; building web UI competes on wrong axis
- Multi-framework (Vue, Svelte, Angular) — React/Vite/TS only for P0

### Architecture Approach

The architecture is a clean 4-layer stack: Entry (Typer CLI) → Orchestration (LangGraph StateGraph with 10 nodes) → Domain Services (15 services with single responsibilities) → Adapters (7 Protocol-based external interfaces). The critical innovation over the design docs is using LangGraph's `context_schema` parameter (verified v1.1.3) for dependency injection via a `ServiceContainer` dataclass, replacing the design docs' anti-pattern of instantiating services inside nodes. All nodes are `async def`, following the "thin node, fat service" pattern (5-15 lines per node, all logic in services).

**Major components:**
1. **ServiceContainer** (`graph/context.py`) — DI container holding all adapters, injected via LangGraph `Runtime[ServiceContainer]`
2. **10 LangGraph Nodes** (`graph/nodes/`) — Thin orchestration wrappers with error boundary wrapper
3. **15 Domain Services** (`services/`) — Business logic: scanner, extractor, generator, validator, classifier, planner, etc.
4. **7 Adapter Protocols** (`adapters/`) — LLM, Filesystem, Git, Sandbox, Playwright, ScreenshotDiff, BuildRunner
5. **40+ Pydantic Models** (`models/`) — Pure data layer, depends on nothing, everything depends on it
6. **Workspace Manager** (`workspace/`) — `.ddk/` directory, checkpoints, rollback

### Critical Pitfalls

12 pitfalls identified with 7 stack-specific addenda. Top 5 with highest impact:

1. **LangGraph state mutation corruption** — Nodes must return new lists (`state["items"] + [new]`), never mutate in-place (`.append()`). Establish immutability convention + contract test in Phase 0. Recovery cost: HIGH (must replay entire pipeline).
2. **SSIM threshold fragility** — 0.92 threshold is an assumption; varies with viewport, font rendering, OS anti-aliasing. Use fixed `data_range=1.0`, pixel-exact viewport control, 6×6 grid for critical regions. Calibrate with fixture screenshots before enabling visual auto-fix rules. Risk: highest-risk single feature.
3. **LLM cost runaway in auto-fix** — $0.10 budget is tight. Pre-check cost before each LLM call, track actual tokens from API response (not estimates), include image token costs. Hard-abort pipeline when cap exceeded.
4. **Subprocess/browser process leaks** — Use `os.setsid` + `os.killpg` for process group management. Playwright cleanup must handle both browser and playwright context failures. Add `conftest.py` fixture asserting no zombie Chromium processes.
5. **Git worktree orphaning** — `WorktreeSandbox.create()` finally block doesn't survive SIGKILL/OOM. Add `git worktree prune` + stale temp dir cleanup at pipeline startup. Register signal handlers for SIGTERM/SIGINT.

## Implications for Roadmap

Based on research, suggested 5-phase structure following the architecture's import dependency chain (models → adapters → services → graph → CLI) and the feature dependency graph.

### Phase 1: Foundation & Core Infrastructure
**Rationale:** Everything depends on models, adapters (Protocols), GraphState, and ServiceContainer. The architecture research proves these must exist before any node logic. Pitfalls research shows 6 of 12 pitfalls must be addressed here (state mutation, edge routing, serialization, context pack determinism, LLM mock quality, process signal forwarding).
**Delivers:** Compilable project skeleton, all 40+ Pydantic models with roundtrip tests, all 7 adapter Protocols + test doubles (FakeLLM, InMemoryFilesystem), ServiceContainer, GraphState with initial_state(), error boundary wrapper, workspace manager, preflight doctor (`ddk doctor`).
**Addresses:** DDK-REQ-001 (Workspace Bootstrap), DDK-REQ-021 (Preflight Doctor), DDK-REQ-016 (Sandbox Policy definitions), DDK-REQ-020 (Reproducibility metadata schemas)
**Avoids:** Pitfall 1 (state mutation — contract tests), Pitfall 2 (edge routing — topology test), Pitfall 9 (Pydantic serialization — roundtrip tests), Pitfall 11 (context pack determinism — sort-before-limit), Pitfall 12 (LLM mock quality — malformed response fixtures), Stack Pitfall B (LangGraph API drift — verify build_ddk_graph compiles)

### Phase 2: Ingestion & Analysis Pipeline
**Rationale:** The feature dependency graph shows a strict chain: intake → repo_scan → intent → plan → generate. Build the first 4 nodes as a linear chain, validating `context_schema` injection works end-to-end. This is the first LLM-calling phase — establishes the Anthropic/OpenAI adapter integration, cost tracking, and structured output parsing patterns that all subsequent phases reuse.
**Delivers:** Working 4-node graph (ingest → repo_scan → intent_extract → plan), LLM adapter with both providers, cost tracker, model router, LLM call recorder, context pack builder.
**Addresses:** DDK-REQ-002 (Multimodal Intake), DDK-REQ-003 (Repo Convention Scan), DDK-REQ-004 (Semantic Intent Model), DDK-REQ-005 (Design System Inference), DDK-REQ-006 (Generation Plan Graph), DDK-REQ-015 (LangGraph State — partial)
**Avoids:** Pitfall 6 (cost runaway — cost tracking from first LLM call), Stack Pitfall A (OpenAI v2 — verify structured output API path), Stack Pitfall G (Anthropic env var — explicit api_key)

### Phase 3: Code Generation & Normalization
**Rationale:** With analysis complete, generation is the core value proposition. Normalization immediately follows to align output with repo conventions before validation. These two nodes complete the "forward path" before the validation loop begins.
**Delivers:** Working 6-node graph (through normalize), generated React/TypeScript components, post-generation normalization (import paths, naming, file placement), full context pack integration.
**Addresses:** DDK-REQ-007 (Code Generation Engine), DDK-REQ-008 (Post-generation Normalizer)
**Avoids:** Pitfall 3 (state size — establish size budgets for generated artifacts)

### Phase 4: Validation & Self-Healing Loop
**Rationale:** The most complex phase. Introduces sandbox execution, Playwright browser automation, SSIM visual regression, failure classification, and the bounded auto-fix retry loop. This phase has the highest pitfall density (4 of 12 pitfalls apply here). The conditional edge routing that creates the fix→validate→fix loop is the most error-prone graph topology.
**Delivers:** Complete 10-node graph with all conditional edges, git worktree sandbox, build/typecheck/lint validation, Playwright screenshot capture, SSIM comparison, failure taxonomy classification, 9 auto-fix repair rules, retry budget controller with oscillation detection, checkpoint/rollback.
**Addresses:** DDK-REQ-009 (Sandboxed Validation), DDK-REQ-010 (Console Capture), DDK-REQ-011 (Visual Regression), DDK-REQ-012 (Bounded Auto-fix), DDK-REQ-013 (Failure Taxonomy), DDK-REQ-019 (Rollback & Checkpoint), DDK-REQ-015 (LangGraph State — complete), DDK-REQ-016 (Sandbox Execution Policy — runtime)
**Avoids:** Pitfall 4 (Playwright leaks — process group cleanup), Pitfall 5 (worktree orphaning — prune on startup), Pitfall 7 (auto-fix oscillation — A→B→A detection), Pitfall 8 (subprocess signals — os.setsid + os.killpg), Pitfall 10 (SSIM calibration — fixture-based threshold tuning)

### Phase 5: Certification, CLI & E2E
**Rationale:** Final assembly. The certify node aggregates all evidence, computes scorecard, makes release decision. CLI integration wraps everything with Typer commands, Rich progress output, and proper exit codes. E2E tests validate the complete pipeline with FakeLLM + fixture repos.
**Delivers:** Complete `ddk run` command, evidence pack export, benchmark scorecard, release decision gate (ready/blocked/manual-review), structured CLI output with progress bars, non-zero exit codes for failures, `ddk rollback` escape hatch.
**Addresses:** DDK-REQ-014 (Evidence Pack), DDK-REQ-017 (Benchmark Scorecard), DDK-REQ-018 (Release Decision Gate), DDK-REQ-020 (Reproducibility — full), DDK-REQ-015 (LangGraph State — final)
**Avoids:** Stack Pitfall F (Typer import time — lazy imports for ≤2s startup)

### Phase Ordering Rationale

- **Bottom-up by import dependency:** models → adapters → services → graph → CLI. This matches the architecture's enforced import rules and ensures each layer is testable in isolation before composition.
- **Feature dependency chain:** The FEATURES.md dependency graph shows a strict linear chain for the first 8 requirements (intake through normalize), then a branching validation loop. Phases 2-3 follow the linear chain; Phase 4 introduces branching.
- **Pitfall front-loading:** 6 of 12 pitfalls are Phase 0/Foundation issues. Addressing them first prevents expensive rework. The remaining pitfalls cluster in Phase 4 (validation), which is why that phase needs the most careful planning.
- **LLM integration early:** Phase 2 establishes all LLM patterns (adapter, cost tracking, structured output parsing, error handling for malformed responses) so that Phases 3-4 reuse proven patterns.
- **Deferred complexity:** Visual regression (SSIM) and auto-fix are the highest-complexity, highest-risk features. They come in Phase 4 after the simpler generation path is working, allowing threshold calibration with real generated output.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (Ingestion & Analysis):** OpenAI SDK v2 structured output API — verify `beta.chat.completions.parse()` path. Anthropic `tool_use` schema integration with Pydantic `model_json_schema()`. Context pack size budgeting for $0.10 cost target.
- **Phase 4 (Validation & Self-Healing):** SSIM threshold calibration methodology. Auto-fix rule interaction testing (oscillation scenarios). Playwright `networkidle` vs `domcontentloaded` for Vite HMR apps. Git worktree concurrent access patterns.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** Well-documented patterns — Pydantic v2 models, Protocol-based adapters, LangGraph StateGraph setup. Design docs provide complete specifications.
- **Phase 3 (Generation & Normalization):** LLM code generation is well-documented across competitors. Prompt engineering patterns are established. Normalization is deterministic rule application.
- **Phase 5 (Certification & CLI):** Typer CLI, Rich output, evidence bundling are straightforward integration work with no novel patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified against PyPI. Direct SDK decision well-justified by dependency weight analysis. Only concern: OpenAI v2 API path needs runtime verification. |
| Features | MEDIUM-HIGH | Table stakes confirmed via 7-competitor source-level analysis. Differentiators validated as genuinely unique. Complexity estimates reasonable. Some competitor analysis based on leaked prompts (may be outdated). |
| Architecture | HIGH | LangGraph `context_schema` verified against live v1.1.3 API. 4-layer architecture with Protocol-based DI is proven pattern. Build order follows import dependencies — mechanically correct. |
| Pitfalls | HIGH | 12 pitfalls derived from design doc analysis + Python ecosystem expertise. Each pitfall has concrete code examples, warning signs, and phase assignments. Stack-specific pitfalls address real version drift risks. |

**Overall confidence:** HIGH

### Gaps to Address

- **SSIM threshold values:** 0.92 is an assumption. Need empirical calibration with 10+ fixture screenshot pairs (matching/non-matching) across macOS and Linux before the threshold can be trusted. Plan a calibration sprint within Phase 4.
- **OpenAI SDK v2 migration:** `beta.chat.completions.parse()` may have moved. Verify during Phase 2 LLM adapter implementation. If broken, the fix is likely a one-line import path change, but it blocks the fallback provider.
- **LangGraph ≥0.2.0 to 1.1.3 compatibility:** Design targets `>=0.2.0` but latest is `1.1.3`. Major version bump. Architecture research verified `context_schema` works on 1.1.3, but other APIs (edge functions, END sentinel, add_sequence) should be smoke-tested early in Phase 1.
- **Auto-fix rule coverage rate:** The 9 repair rules cover known failure families, but what percentage of real failures hit `manual-review-required`? Unknown until real-world usage. Track manual-review rate as a key metric from Phase 4.
- **$0.10 cost budget feasibility:** 4+ LLM calls with potential image inputs and 3 fix retries is tight. Actual cost depends on prompt sizes, context pack sizes, and model pricing. Validate with real API calls during Phase 2 integration testing.
- **Cross-platform SSIM stability:** SSIM scores may vary between macOS (dev) and Linux (CI) due to font rendering differences. Need CI-specific fixtures or platform-aware thresholds.

## Sources

### Primary (HIGH confidence)
- Project design docs (35 documents in `docs/design/`) — complete specifications for all 21 requirements
- LangGraph v1.1.3 live API verification — `context_schema`, `Runtime`, `StateGraph`, `add_sequence`
- PyPI package metadata (2025-07-27) — version verification for all 14 dependencies
- Anthropic SDK 0.86.0 / OpenAI SDK 2.30.0 / Typer 0.24.1 `requires_dist` — transitive dependency verification

### Secondary (MEDIUM confidence)
- **screenshot-to-code** (72K★ GitHub): Pipeline architecture, prompt design, evaluation methodology
- **Aider** (42K★ GitHub): `auto_lint` cycle, reflected_message pattern, repo map approach
- **bolt.new** (16K★ GitHub): WebContainer sandbox, action execution model
- Leaked system prompts: v0 (Vercel), Lovable, Same.dev — sandbox patterns, linter loops, debug workflows

### Tertiary (LOW confidence)
- Competitive positioning analysis based on general AI code generation landscape knowledge (early 2025)
- Auto-fix rule coverage rate predictions — no empirical data exists yet

---
*Research completed: 2025-07-27*
*Ready for roadmap: yes*

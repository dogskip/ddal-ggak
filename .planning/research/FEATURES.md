# Feature Landscape

**Domain:** AI-powered design-to-code delivery pipeline (CLI)
**Researched:** 2025-07-25
**Overall confidence:** MEDIUM-HIGH

## Competitive Landscape Context

Research covered 7 tools with source-level analysis where available:

| Tool | Type | Sandbox | Auto-fix | Visual Check | Repo-aware | Open Source |
|------|------|---------|----------|-------------|------------|-------------|
| **v0** (Vercel) | Design→Code | Vercel Sandbox (Linux VM) | Debug via console.log, iterative chat | Live preview, no automated diff | Partial (Next.js default) | No (prompts leaked) |
| **bolt.new** (StackBlitz) | Prompt→Code | WebContainer (WASM) | User-driven retry | Live preview iframe | No (starts from template) | Yes |
| **screenshot-to-code** | Screenshot→HTML | None | None (one-shot) | Manual human eval (1-4 score) | No | Yes (72K★) |
| **Lovable** (ex-GPT Engineer) | Prompt→Code | Cloud IDE container | Console log → AI debug loop | Live preview iframe | Partial (React/Vite only) | No (prompts leaked) |
| **Same.dev** | URL/Screenshot→Clone | Docker container (Ubuntu) | Linter loop (max 3 retries) | Screenshot via `versioning` tool | Partial (shadcn default) | No (prompts leaked) |
| **Aider** | Code editing | None (runs locally) | Lint→ask→re-prompt (auto_lint) | None | Yes (deep repo map) | Yes (42K★) |
| **Replit** | Prompt→Code | Nix-based container | AI-guided debugging | Live preview | Template-based | No |

**Key insight:** None of these tools implement ddalggak's full closed-loop pipeline (generate→validate→visual-regress→auto-fix→certify). The closest are Aider (lint auto-fix) and Same.dev (bounded linter loop), but neither does visual regression or sandboxed runtime validation systematically.

---

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Dependencies | Evidence |
|---------|-------------|------------|--------------|----------|
| **Screenshot/image intake** | Core input modality. v0, screenshot-to-code, Same.dev all accept images. Without this, tool isn't "design-to-code." | Low | DDK-REQ-002 | All competitors support this. HIGH confidence. |
| **Prompt/text intake alongside images** | Users always need to guide generation beyond the visual. Every tool in the space supports supplementary text prompts. | Low | DDK-REQ-002 | All competitors support this. HIGH confidence. |
| **React/TypeScript code generation** | React is the dominant target stack. v0 defaults to Next.js, Lovable to React/Vite, Same.dev to React/Vite. Generating non-React code is a niche. | Med | DDK-REQ-007 | Market consensus. HIGH confidence. |
| **Buildable output (build passes)** | Generated code that doesn't build is useless. v0 runs in a live sandbox; bolt.new uses WebContainers; Same.dev runs linter after every edit. Build-passing is baseline expectation. | Med | DDK-REQ-009 | Every tool with a sandbox validates builds. HIGH confidence. |
| **Type-safe output (TypeScript strict)** | TypeScript users expect type-correct code. v0 prompt enforces "strict mode," Same.dev uses linter checks. | Med | DDK-REQ-009 | v0 and Same.dev both enforce this. HIGH confidence. |
| **Lint-clean output** | Same.dev runs `run_linter` after every significant edit. Aider runs lint post-edit automatically. Users expect clean code. | Low | DDK-REQ-009 | Aider (auto_lint=True default), Same.dev (explicit linter loop). HIGH confidence. |
| **Existing repo convention awareness** | Aider excels here with deep repo maps. v0 reads existing project files. Same.dev uses grep/search. Code that ignores conventions creates debt. | High | DDK-REQ-003, DDK-REQ-005 | Aider's key differentiator; v0 reads project context. MEDIUM confidence on complexity. |
| **CLI-based interface** | Target persona is developer. Aider, screenshot-to-code all have CLI. Non-technical tools (v0, Lovable) use web UI but ddalggak's CLI-first is appropriate for dev audience. | Low | DDK-REQ-021 | Aider demonstrates CLI-first works. HIGH confidence. |
| **Structured output from LLM (JSON schema)** | All serious tools force structured output. v0 uses tool_use schema, screenshot-to-code uses tool-based output, Aider uses edit formats (search/replace, whole file, etc.). Free-text generation is unreliable. | Med | DDK-REQ-004, DDK-REQ-007 | Industry consensus. HIGH confidence. |
| **Temperature=0 / deterministic mode** | ddalggak's prompt design mandates temperature=0. Same.dev and Aider also default to deterministic settings. Reproducibility is expected in dev tools. | Low | DDK-REQ-020 | Common practice. HIGH confidence. |

---

## Differentiators

Features that set ddalggak apart. Not expected by default, but create significant value.

| Feature | Value Proposition | Complexity | Dependencies | Evidence / Competitive Gap |
|---------|-------------------|------------|--------------|----------------------------|
| **Automated visual regression (SSIM-based)** | **No competitor does this automatically.** screenshot-to-code uses manual human scoring (1-4 scale). v0/Lovable rely on live preview for human eyeballing. ddalggak's automated SSIM comparison against reference screenshots is unique in the CLI tool space. | High | DDK-REQ-011, DDK-REQ-010 (Playwright) | screenshot-to-code uses human eval. No tool automates reference vs generated diff. HIGH confidence this is a differentiator. |
| **Deterministic auto-fix rulebook (not LLM re-prompting)** | All competitors that retry use LLM re-prompting (Same.dev sends linter errors back to LLM, Aider sends lint errors as "reflected_message"). ddalggak's approach of deterministic rule-based repair (9 fixed rules, no creative generation) is architecturally distinct and more predictable. | High | DDK-REQ-012, DDK-REQ-013 | Aider: lint errors → prompt → hope for fix. Same.dev: linter → re-prompt → max 3 loops. ddalggak: classified failure → fixed rule → bounded patch. HIGH confidence this is novel. |
| **Evidence pack with full audit trail** | No competitor produces a replayable evidence bundle. v0 has debug logs. Same.dev has versioning. But none package all artifacts (LLM calls, screenshots, diffs, fix attempts, scorecard) into a single replayable bundle. | Med | DDK-REQ-014, DDK-REQ-020 | Unique to ddalggak. HIGH confidence. |
| **Failure taxonomy with stable IDs** | Competitors don't classify failures systematically. Aider shows raw lint output. Same.dev shows raw linter errors. ddalggak's taxonomy (BUILD-001..VISUAL-003) enables tracking, metrics, and rule-based repair selection. | Med | DDK-REQ-013 | No competitor has formalized failure classification. HIGH confidence. |
| **Bounded retry with exhaustion escalation** | Same.dev caps at 3 linter fix loops then "ask user what to do." Aider asks user "Attempt to fix lint errors?" (interactive). ddalggak's bounded budget with automatic escalation to manual-review (not just giving up) with blocker report is more principled. | Med | DDK-REQ-012 | Same.dev: 3 loop cap but UX is "stop and ask." ddalggak: structured escalation. MEDIUM confidence on value. |
| **Git worktree sandbox isolation** | bolt.new uses WebContainers (WASM). v0 uses Vercel Sandbox (Linux VM). Same.dev uses Docker. ddalggak's git worktree approach is zero-dependency (no Docker needed), fast (<1s init vs 3-30s for Docker), and integrates naturally with rollback. No other CLI tool uses this pattern. | Med | DDK-REQ-009, DDK-REQ-016, DDK-REQ-019 | Unique approach. Most competitors require Docker or cloud. MEDIUM confidence — novel but unproven at scale. |
| **Release decision gate (ready/blocked/manual-review)** | No competitor has a formal release gate. Tools either succeed or fail. ddalggak's multi-condition gate (scorecard + blockers + evidence completeness + rollback safety) creates a real quality bar. | Med | DDK-REQ-018, DDK-REQ-017 | Completely unique. HIGH confidence this differentiates. |
| **Post-generation normalization** | v0 follows Next.js conventions by default. Lovable follows React/Vite patterns. But none have an explicit normalization pass that aligns naming/imports/tokens/file placement to the *specific target repo's* conventions after generation. | Med | DDK-REQ-008 | Aider respects repo context during generation, but has no post-generation alignment. MEDIUM confidence. |
| **Semantic intent extraction as intermediate representation** | Most tools go screenshot→code directly (screenshot-to-code) or prompt→code (v0, Lovable). ddalggak extracts an intermediate IntentGraph (layout regions, components, interactions with confidence scores) before code generation. This enables better planning and failure diagnosis. | High | DDK-REQ-004, DDK-REQ-005 | screenshot-to-code goes directly to HTML. v0 generates directly. ddalggak's intermediate IR is architecturally distinct. MEDIUM confidence on practical value — adds latency and cost. |

---

## Anti-Features

Features to explicitly NOT build. Lessons from competitors.

| Anti-Feature | Why Avoid | What Competitors Do | What to Do Instead |
|--------------|-----------|---------------------|-------------------|
| **Unbounded LLM re-prompting for fixes** | Same.dev caps at 3, but still re-prompts the LLM with raw error text hoping it "figures it out." This is stochastic, expensive, and unpredictable. ddalggak's design docs correctly identify this as an anti-pattern. | Aider: sends lint errors as reflected_message for another LLM call. Same.dev: sends linter errors back to model, caps at 3. | Deterministic repair rules (FX-BUILD-IMPORT-001, etc.) with classified failure → fixed rule mapping. Budget is per-rule, not per-LLM-call. |
| **Live preview / interactive web UI** | v0, Lovable, bolt.new, Same.dev are all web-based with live previews. This is **their** differentiator for non-technical users. ddalggak targets developers with CLI-first approach. Building a web UI in v1 would be scope creep and compete on the wrong axis. | v0: iframe preview. Lovable: iframe preview. bolt.new: WebContainer preview. | CLI output with evidence pack paths. `ddk` commands produce artifacts, not interactive experiences. Web UI is explicitly out of scope (Phase 4+). |
| **Multi-framework generation (Vue, Svelte, Angular)** | screenshot-to-code supports HTML/Tailwind/React/Vue/Bootstrap/Ionic stacks, but quality degrades outside React. Spreading across frameworks dilutes quality. | screenshot-to-code: 6 stacks, quality varies. v0: Next.js only. Lovable: React/Vite only. | React/Vite/TypeScript only for P0. All design docs correctly scope to this. |
| **Full application generation (multi-page, routing, API)** | v0 generates full Next.js apps with routing, data fetching, database integrations. This is exponentially more complex. ddalggak's P0 correctly limits to single page/component. | v0: full Next.js apps. Lovable: full apps with Supabase. bolt.new: full-stack with WebContainers. | Single page or single component. The prompt design doc (16-prompt-design.md) correctly states: "Multi-page layouts, route-based navigation, and API-backed data flows are OUT OF SCOPE." |
| **Real-time streaming code preview** | v0 and bolt.new stream code changes as they're generated, showing live updates. Impressive UX but irrelevant for CLI tool and adds significant complexity. | v0: streaming code preview. bolt.new: streaming file writes. screenshot-to-code: streams HTML updates. | Batch generation with final output. CLI doesn't benefit from streaming preview. |
| **Docker-based sandbox for P0** | Same.dev uses Docker (Ubuntu 22.04). Replit uses Nix containers. These provide stronger isolation but add 3-30s startup and Docker dependency. ddalggak's ADR-021 correctly defers Docker to v2. | Same.dev: Docker. Replit: Nix. v0: Vercel Sandbox. | git worktree for P0. Docker upgrade in v2 when security isolation matters more. |
| **Dependency installation / package.json modification** | The auto-fix rulebook correctly forbids adding new dependencies. Tools like v0 and bolt.new freely install packages because they control the environment. For a CLI tool working on user repos, adding dependencies is dangerous. | v0: auto-installs via pnpm. bolt.new: installs in WebContainer. | Auto-fix must never add dependencies or modify lockfiles. This is a security and trust boundary. |
| **Website cloning** | Same.dev has explicit website cloning workflows (scrape → analyze → reproduce). This is a different product category. | Same.dev: web_scrape → clone workflow. screenshot-to-code: screenshot → HTML (similar but simpler). | Focus on mockup/design → component code. Not URL → clone. |

---

## Feature Dependencies

```
DDK-REQ-021 (Preflight Doctor)
    └── All other features (must pass before any pipeline execution)

DDK-REQ-001 (Workspace Bootstrap)
    └── DDK-REQ-002 (Multimodal Intake)
        └── DDK-REQ-003 (Repo Convention Scan)
        └── DDK-REQ-004 (Semantic Intent Model) ← requires image from intake
            └── DDK-REQ-005 (Design System Inference) ← enriches intent
                └── DDK-REQ-006 (Generation Plan Graph) ← combines intent + repo + design system
                    └── DDK-REQ-007 (Code Generation) ← executes plan
                        └── DDK-REQ-008 (Post-gen Normalizer) ← fixes convention drift

DDK-REQ-009 (Sandboxed Runtime Validation) ← requires generated code
    ├── DDK-REQ-016 (Sandbox Execution Policy) ← defines sandbox rules
    └── DDK-REQ-010 (Console & Error Capture) ← requires sandbox runtime
        └── DDK-REQ-011 (Visual Regression) ← requires running app + Playwright

DDK-REQ-013 (Failure Taxonomy) ← classifies validation failures
    └── DDK-REQ-012 (Bounded Auto-fix Loop) ← uses taxonomy to select rules
        └── DDK-REQ-019 (Rollback & Checkpoint) ← checkpoint before each fix

DDK-REQ-015 (LangGraph State Orchestration)
    └── Orchestrates all above in correct order with state management

DDK-REQ-014 (Evidence Pack Builder) ← collects artifacts from all stages
DDK-REQ-020 (Reproducibility Metadata) ← records LLM call details
DDK-REQ-017 (Benchmark Scorecard) ← scores final output
    └── DDK-REQ-018 (Release Decision Gate) ← aggregates all evidence for go/no-go
```

---

## Detailed Feature Analysis by Category

### 1. Visual Comparison Approaches

| Approach | Used By | How It Works | Pros | Cons |
|----------|---------|-------------|------|------|
| **Human eval (manual scoring)** | screenshot-to-code | 16-image eval dataset, human rates 1-4 | Ground truth quality | Not automatable, slow, subjective |
| **Live preview (human eyeballing)** | v0, Lovable, bolt.new | Iframe shows running app, user checks visually | Fast feedback, intuitive | Not automated, no regression detection |
| **Screenshot tool for versioning** | Same.dev | `versioning` tool captures screenshots; AI analyzes them | AI can spot issues | No reference comparison, no metric |
| **SSIM structural comparison** | **ddalggak** (planned) | scikit-image SSIM on Playwright screenshots vs reference | Automated, deterministic, measurable | Threshold calibration needed, sensitive to viewport/font rendering |
| **Pixel diff ratio** | **ddalggak** (planned) | Changed pixel percentage calculation | Simple, catches gross differences | Too sensitive to antialiasing, minor spacing |
| **Critical region overlap** | **ddalggak** (planned) | Checks if key UI elements (CTA, hero, nav) are present | Catches most important failures | Requires accurate region detection from intent |

**Recommendation for ddalggak:** The SSIM + critical region approach is correct. Key calibration insight from screenshot-to-code's eval methodology: they run 3 tests per config and average scores, acknowledging variance. ddalggak should similarly expect variance and use threshold profiles (already designed in 07-verification-release.md with assumption→provisional→calibrated states).

**Risk:** SSIM thresholds are fragile across different viewport sizes, font rendering engines, and OS-level anti-aliasing. The 0.92 threshold is an assumption that needs empirical calibration with golden fixtures. **This is the single highest-risk feature in the pipeline.**

### 2. Auto-fix Strategies

| Strategy | Used By | How It Works | Effectiveness | Risk |
|----------|---------|-------------|---------------|------|
| **LLM re-prompt with error context** | Aider, Same.dev, Lovable | Feed error output back to LLM, ask it to fix | Medium (LLM may or may not understand) | Stochastic, expensive, may introduce new errors |
| **Lint → commit → reflect** | Aider | Run lint, commit partial result, feed errors as "reflected_message" for next LLM turn | Good for lint; poor for runtime errors | Requires user confirmation ("Attempt to fix?") |
| **Bounded linter loop** | Same.dev | Run linter after edits, re-prompt up to 3 times | Good for syntax/lint; nothing for runtime | Hard 3-loop cap, then "ask user" |
| **Debug console → AI analysis** | Lovable | Read console logs, AI analyzes and suggests fix | Good for runtime errors visible in console | Requires running app, AI interpretation is fuzzy |
| **Deterministic rule-based repair** | **ddalggak** (planned) | Classify failure → select fixed repair rule → bounded patch → re-validate | Predictable, testable, measurable | Limited to known failure patterns; novel errors go to manual-review |

**Recommendation for ddalggak:** The deterministic approach is correct AND is a genuine differentiator. Competitors' "re-prompt the LLM" approach has fundamental problems: (1) no guarantee of improvement, (2) cost increases linearly, (3) new errors can be introduced, (4) non-reproducible. ddalggak's 9-rule catalog with the AutoFixPlanner is more principled.

**Critical gap to validate:** The 9 rules cover build/type/lint/runtime/visual families, but there will be uncategorized failures. The BUILD-001 "catch-all" pattern and ManualReviewRequired escalation handle this correctly. The risk is that too many cases hit manual-review in practice, making the auto-fix feel useless. **Track the manual-review-required rate as a key metric.**

### 3. Sandbox Execution Patterns

| Pattern | Used By | Init Time | Isolation Level | Dependency |
|---------|---------|-----------|-----------------|------------|
| **WebContainer (WASM)** | bolt.new | ~2-5s | Browser-level (no filesystem access outside container) | @webcontainer/api (StackBlitz proprietary) |
| **Vercel Sandbox (Linux VM)** | v0 | ~3-10s | Full VM isolation | Vercel infrastructure |
| **Docker container** | Same.dev, Replit | 3-30s | Full container isolation (namespace, network) | Docker daemon required |
| **None (local execution)** | Aider, screenshot-to-code | 0s | None — runs in user's environment | N/A |
| **git worktree** | **ddalggak** (planned) | <1s | Directory-level (process isolation only) | git >= 2.30 |

**Recommendation for ddalggak:** git worktree is the right choice for P0. Key advantages:
1. Zero external dependencies (git is universally available)
2. Sub-second initialization (vs 3-30s for Docker)
3. Natural git checkpoint/rollback integration
4. Sufficient for developer-facing CLI tool (user trusts their own machine)

**Known security gap (correctly documented in ADR-021):** Network access is unrestricted, environment variable leakage is possible (mitigated by env whitelist). This is acceptable for P0 because the user is running on their own machine against their own repo. Docker upgrade in v2 is the right plan.

### 4. LLM Prompt Strategies for Code Generation

| Strategy | Used By | How It Works | Token Efficiency |
|----------|---------|-------------|------------------|
| **Direct screenshot→HTML (single prompt)** | screenshot-to-code | System prompt + image + "generate exactly like screenshot" | High (single call, ~3,700 tokens) |
| **Agentic with tools** | v0, Same.dev, Lovable | LLM has file read/write/search tools, iterates autonomously | Low (many tool calls, high total cost) |
| **Repo map + edit format** | Aider | Build repo map via tree-sitter, use search/replace edit format | Medium (repo map can be large) |
| **Multi-stage pipeline** | **ddalggak** (planned) | Intent extract → Plan → Generate (per-node) → Normalize | Medium (4+ LLM calls, each focused) |

**Recommendation for ddalggak:** The multi-stage approach is architecturally sound but has a cost/latency tradeoff. With 4+ LLM calls at ~$0.01-0.03 each, staying under the $0.10 budget for P0 is tight but achievable with Claude Sonnet + temperature=0.

**Key insight from v0:** v0's prompt forces structured output through tool_use schemas (same as ddalggak's `tool_use` approach with Pydantic model JSON schemas). This is the correct pattern. screenshot-to-code's older approach of asking for raw HTML is less reliable.

**Key insight from Aider:** Aider's repo map (built via tree-sitter AST analysis) is the most sophisticated context-building approach in the space. ddalggak's RepoConventionScanner should aspire to this level of understanding, though the current design (package.json + sample components + file tree) is simpler and likely sufficient for P0.

### 5. Failure Recovery Patterns

| Pattern | Used By | Recovery Model | User Control |
|---------|---------|----------------|-------------|
| **User-driven retry** | v0, Lovable | User says "that's wrong, fix X" in chat | Full user control, high latency |
| **Automatic lint re-prompt** | Aider | `auto_lint=True` → lint fails → errors fed back to LLM → user asked "Attempt to fix?" | Semi-automatic (user must confirm) |
| **Bounded linter retry** | Same.dev | Run linter → fix → retry up to 3 times → stop if unresolved | Automatic with hard cap |
| **Version/rollback** | Same.dev | `versioning` tool creates snapshots; user can "Revert to..." | User-initiated rollback |
| **Git checkpoint + auto-rollback** | **ddalggak** (planned) | Checkpoint before each fix attempt → restore on regression → escalate on exhaustion | Automatic with `ddk rollback` escape hatch |

**Recommendation for ddalggak:** The checkpoint + auto-rollback is superior to competitors' approaches because:
1. Rollback is automatic on regression (not user-initiated like Same.dev)
2. Each fix attempt is isolated (regression in fix N doesn't corrupt fix N-1's state)
3. Evidence trail shows exactly what was tried and why it failed

**Critical difference from competitors:** Aider asks the user whether to attempt fixes. Same.dev stops and asks. ddalggak is fully automatic within the budget, then produces a structured blocker report. This is the right design for a CLI pipeline tool — the user runs `ddk run` and gets a result, not a conversation.

---

## MVP Recommendation

### Must ship (P0 Table Stakes — without these, tool doesn't function):

1. **Workspace Bootstrap** (DDK-REQ-001) — Foundation for everything
2. **Multimodal Intake** (DDK-REQ-002) — Can't generate without input
3. **Code Generation Engine** (DDK-REQ-007) — Core value proposition
4. **Sandboxed Runtime Validation** (DDK-REQ-009) — Build must pass or tool is useless
5. **Preflight Doctor** (DDK-REQ-021) — Must validate environment before running

### Must ship (P0 Differentiators — without these, tool is just another code generator):

6. **Repo Convention Scan** (DDK-REQ-003) — What separates ddalggak from screenshot-to-code
7. **Failure Taxonomy** (DDK-REQ-013) — Enables intelligent auto-fix
8. **Bounded Auto-fix Loop** (DDK-REQ-012) — Core "self-correcting" promise
9. **Visual Regression Runner** (DDK-REQ-011) — Unique automated quality gate
10. **Evidence Pack Builder** (DDK-REQ-014) — Proves "evidence-gated delivery" claim

### Important but could be simplified:

11. **Semantic Intent Model** (DDK-REQ-004) — Could be simplified to direct generation in MVP, but losing this loses diagnostic capability. Keep but accept lower confidence thresholds initially.
12. **Generation Plan Graph** (DDK-REQ-006) — For single component P0, could be a flat list instead of full DAG. But graph structure enables future multi-component support.
13. **Benchmark Scorecard** (DDK-REQ-017) — Valuable for tracking quality over time, but not strictly needed for first working pipeline. Can emit minimal scorecard.
14. **Release Decision Gate** (DDK-REQ-018) — Simple pass/fail initially; full multi-condition matrix can evolve.

### Defer if timeline pressure (but don't cut):

15. **Design System Inference** (DDK-REQ-005) — Falls back to repo conventions if not available
16. **Post-generation Normalizer** (DDK-REQ-008) — Can be partial (just import path fixing)
17. **Comparative Benchmark** (DDK-REQ-017) — Needs baseline data that won't exist at first
18. **Reproducibility Metadata** (DDK-REQ-020) — Record LLM calls but defer full replay capability

---

## Complexity Estimates by Requirement

| Requirement | Estimated Complexity | Rationale |
|-------------|---------------------|-----------|
| DDK-REQ-001 (Workspace Bootstrap) | **Low** | File/directory creation, idempotent init |
| DDK-REQ-002 (Multimodal Intake) | **Low-Med** | Image validation, schema creation, but straightforward |
| DDK-REQ-003 (Repo Convention Scan) | **Med** | File tree analysis + LLM call for profile extraction |
| DDK-REQ-004 (Semantic Intent) | **High** | Multimodal LLM call + structured output parsing + confidence scoring |
| DDK-REQ-005 (Design System Inference) | **Med** | Token/spacing analysis, mostly deterministic from repo |
| DDK-REQ-006 (Generation Plan) | **Med** | LLM call + graph construction + topological sort |
| DDK-REQ-007 (Code Generation) | **High** | Core LLM integration, prompt engineering, file writing |
| DDK-REQ-008 (Normalizer) | **Med-High** | AST-level transformations, import path resolution |
| DDK-REQ-009 (Sandboxed Validation) | **High** | Process management, timeout handling, result aggregation |
| DDK-REQ-010 (Console Capture) | **Med-High** | Playwright browser automation, event correlation |
| DDK-REQ-011 (Visual Regression) | **High** | Screenshot capture + SSIM + critical region detection + threshold calibration |
| DDK-REQ-012 (Auto-fix Loop) | **High** | Rule selection, patch generation, re-validation orchestration |
| DDK-REQ-013 (Failure Taxonomy) | **Med** | Pattern matching, classification logic |
| DDK-REQ-014 (Evidence Pack) | **Med** | Artifact collection, bundling, replay schema |
| DDK-REQ-015 (LangGraph State) | **High** | State machine design, context budgeting, retry logic |
| DDK-REQ-016 (Sandbox Policy) | **Med** | Allowlist enforcement, path validation |
| DDK-REQ-017 (Benchmark Scorecard) | **Med** | Scoring formula, artifact generation |
| DDK-REQ-018 (Release Decision) | **Med** | Multi-condition aggregation, decision algorithm |
| DDK-REQ-019 (Rollback/Checkpoint) | **Med** | Git operations, checkpoint management |
| DDK-REQ-020 (Reproducibility) | **Low-Med** | Metadata recording, schema versioning |
| DDK-REQ-021 (Preflight Doctor) | **Low** | Environment checks, remediation hints |

---

## Sources

### Source-level analysis (HIGH confidence):
- **screenshot-to-code**: GitHub repo (72K★), `backend/prompts/`, `backend/evals/`, `Evaluation.md` — pipeline architecture, prompt design, evaluation methodology
- **Aider**: GitHub repo (42K★), `aider/coders/base_coder.py`, `aider/linter.py` — auto_lint cycle, reflected_message pattern, search/replace edit format
- **bolt.new**: GitHub repo (16K★), `app/lib/runtime/action-runner.ts`, `app/lib/webcontainer/` — WebContainer sandbox, action execution model

### Leaked system prompts (MEDIUM confidence — may be outdated):
- **v0**: System prompt from x1xhlol/system-prompts-and-models-of-ai-tools — Vercel Sandbox, debug logging, Next.js defaults, tool architecture
- **Lovable**: Agent prompt — React/Vite/Tailwind stack, console log debugging, discussion-first workflow
- **Same.dev**: Full system prompt — Docker container, linter loop (max 3), versioning, website cloning, shadcn defaults

### Training data synthesis (LOW confidence):
- Competitive positioning analysis and market observations based on general knowledge of AI code generation space as of early 2025

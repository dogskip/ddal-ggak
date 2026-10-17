# Changelog

All notable changes to ddalggak (ddk) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Changed — public response contract

- **Breaking:** all JSON-capable CLI commands and MCP tools use the `ddk/2` response envelope.
  The canonical on-disk `verified-change/1` records remain unchanged under `data`.
  Input/approval errors exit 3, unavailable execution exits 4, replay/current-source integrity failures
  exit 5, usage errors retain 2, acceptance failures use 1 and cancellation retains 130.
  Missing legacy cases and parsing failures now produce structured JSON.
  See the generated [exit-code registry](docs/EXIT-CODES.md).

### Changed — host installation

- **Breaking:** host installation now renders canonical Agent Skills into official host paths.
  Claude MCP uses project `.mcp.json`, Gemini uses TOML, Codex uses `.agents/skills`,
  OpenCode uses direct `mcp.ddk` configuration, Copilot uses prompt files and Cursor uses MDC.
  Existing legacy files are never silently deleted. Global Copilot/Cursor rules are unsupported.
- `install --all` selects detected hosts only. `--dry-run --json` previews the plan;
  `uninstall --host NAME` restores only hash-matching owned files and reports edited files as conflicts.
  Credentials in MCP configurations remain excluded from source/model inputs.

### Fixed

- Isolated native test reports now use the app's private source copy instead of the observer-only
  `/results` mount. Bounded regular-file checks reject missing, linked, oversized and invalid UTF-8
  reports; native report bytes remain in hash-bound evidence alongside stdout and stderr.
  App access to observer criteria and results remains prohibited.

### Added

- Three canonical agent skills: reviewed-plan verification, bounded evidence inspection and Design Studio.
  Host execution, provider transfer and application retain explicit, separate approval boundaries.
  CLI examples are checked against the actual command tree; a recorded-response dry-run test uses no paid model.

- Python, JavaScript and browser repository reproduction fixtures with valid-change, missed-target
  and preservation-regression variants, host and Linux-container execution, installed-wheel checks,
  and a receipt summarizer that rejects incomplete matrices and skipped checks.

### Added — evidence-bound harness runtime

- `init --discover` creates unapproved static/headless acceptance drafts; explicit approval shares
  the sealed-case flow/check compiler and never overwrites existing configuration.
- Deterministic failure/AX/visual excerpts, hash-linked raw evidence retrieval, stable repair prefixes,
  exact-error stall protection and canonical revalidation of resolved cross-case lessons.
- `change gate`, optional project Stop/pre-push guards (including actual pushed commit tips),
  `change replay` and MCP metadata/evidence tools with strict owner and input boundaries.
- Sixteen logical SQLite/FTS5 tables, optional backward-compatible Run metadata, observed cache usage,
  actual owned-copy cleanup receipts and source-stable atomic rebuild. Public schema/column parity tests.
- Independent review counterexamples cover configuration/run races, imported draft bypass, malformed
  approval, host execution grants, mismatched push commits, timing noise and same-step AX comparison.



### Added — one-command verified changes

- Hash-free `ddk init`/`change init`, Git-ref snapshots, explicit deletion authority, and `ddk up`:
  verify → bounded repair → export → candidate-bound apply preview/application.
- Rebuildable SQLite/FTS5 projection (expanded to sixteen logical tables above) with canonical-write hooks, atomic reindex, masked failure
  lessons and bounded metadata queries. Canonical JSON paths and verdict names remain compatible.
- Native JUnit/pytest/Jest/Vitest/Playwright reports with explicit skip allowance; owned policy checks;
  headless PNG/AX/DOM probe and immutable reference registration; exact search/replace proposals.
- Anthropic, compatible API and restricted CLI provider bridges, dated prices and fail-closed unknown
  billing. Verified-change MCP tools with strict inputs and explicit owner/caller grants.
- Strict mypy in addition to existing Pyright checks; adversarial deletion/application/catalog tests.

### Changed

- Standalone `change repair`, `up` and MCP repair share provider/price selection, lazy provider
  construction and explicit overrides. A valid dated Anthropic quote no longer needs a manual file.
- **Breaking CLI change:** plain `doctor` and its JSON/dry-run forms share observed readiness,
  safe settings diagnostics and blocked exit 2 (previously 1 for the legacy plain command).
  Explicit browser installation remains available; dry-run suppresses it.
- Post-verification source changes and application conflicts block the overall command even when
  its saved verification verdict is ready. Probe records extra blank-page denial, awaits pending
  responses and retains bounded page diagnostics after a missing-selector failure.
- **Breaking CLI change:** `ddk init PATH` is now `ddk workspace-init PATH`.
  `ddk init --request ...` compiles an immutable verification case.
- [One-command guide](docs/ONECLICK.md), Korean guide and catalog fields document actual limits;
  paid-model effectiveness and independent multi-project adoption remain separate evidence priorities.

### Changed

- **Breaking safety change:** legacy `ddk apply --force`, `--allow-blocked` and whole-repository
  `ddk rollback` now refuse execution. Resolve conflicts explicitly; managed `ddk change recover`
  handles interrupted owned applies, not arbitrary undo.
- Public development is consolidated on `main`. Internal plans, design/review notes, launch drafts
  and raw execution evidence stay local and are no longer tracked; prior Git history is retained.
- Runtime contract schema now lives in `src/ddk/assets/verified-change/`; synthetic contract examples
  live in `tests/fixtures/verified-change/`. Source/wheel checks reject internal material and verify
  required assets. The public docs and roadmap distinguish shipped behavior from next priorities.

### Added

- `ddk change repair`: approved source-run scope, explicit provider/price grants, one durable budget
  across proposals and independent rechecks, immutable round evidence, replay conflict detection and
  cycle/limit/unknown-cost stops. Existing managed apply/recovery consumes the final verified result.
- A bounded Anthropic attempt preserves the exact output reservation and observed model identity;
  unsupported or missing usage remains unknown. Ready records reject unsettled calls, and recursive
  source references stop at depth 32. Real headless repair-to-apply coverage uses recorded proposals.

#### Existing-change verification

- `ddk change verify/status/export/apply/recover`: fixed cases, explicit baseline/candidate,
  requirement mapping, bounded records/evidence, managed apply and interruption recovery.
- Default isolated local Docker app/checker execution with immutable images, environment checks,
  independent headless browser observations, output accounting and owned-container cleanup.
  Explicit trusted-local CLI execution is a separate assurance; there is no automatic fallback.
- MCP `ddk_verify` and `ddk_status` use the same service and storage, with isolated-only execution.
  The [guide](docs/VERIFIED-CHANGES.md) states required inputs and actual acceptance limits;
  integrated setup, repair and authorization are described in the [one-command guide](docs/ONECLICK.md).

#### The loop that checks itself: design image → code → real browser → repair → verdict
- **Screenshot comparison in a real browser.** The built app is served on loopback and opened in
  headless Chromium (Playwright) at the size of the design image; the full-page screenshot is compared
  with the design by block SSIM (Pillow) plus the share of the page that differs strongly. A comparison
  passes at SSIM ≥ 0.92 and ≤ 3 % mismatch (`--ssim-threshold`, `--max-mismatch`, `DDK_SSIM_THRESHOLD`,
  `DDK_MAX_MISMATCH_RATIO`); `--visual/--no-visual` and `DDK_VISUAL_CHECK` switch it, and a waiver is
  recorded in the scorecard and shown in the report. The browser may only reach loopback addresses.
  Preview servers: Vite, Next.js, Astro.
- **Visual repair, rule R-10.** A failed comparison goes back to the model with the design, the
  screenshot and a red difference image; only markup and styling may change, and code diagnostics are
  fixed first. Answers that are empty, truncated, or silence the checker (`any`, `@ts-ignore`,
  `eslint-disable`) are discarded.
- **Checks come from the project.** `services/toolchain.py` reads `package.json`, lockfiles,
  `tsconfig.json` and the ESLint configuration to choose build, type-check and lint; a step that does
  not apply is reported as skipped with its reason, and a run in which nothing was verified is `blocked`.
- **`ddk demo`**: the whole loop on a bundled Vite + React + TypeScript project with a recorded model
  reply, so it needs no API key. Dependency install, build, type-check, lint, preview, Chromium and
  the comparison are real; the first draft misses the design and the loop repairs it.
- **`ddk report`**: one self-contained HTML evidence report per case (verdict, every comparison round
  with the red difference image and an overlay slider, fixes, checks, scorecard, run details). Written
  automatically after `ddk run` and `ddk demo`; `--open` shows it. Every comparison round is kept under
  `artifacts/visual/round-N/`.
- **`ddk apply`**: copies the files of a `ready` case into the repository only where the repository
  still holds the version the run started from; conflicts and unsafe paths stop everything; replaced
  files are backed up in the case folder (`--dry-run` previews writes; force options are disabled).
- **First run without friction.** `ddk run <image>` works without `-p`; a Chrome, Edge or Chromium
  that is already installed is used when Playwright has none; `ddk doctor --install-browser` downloads
  Playwright's headless Chromium, `ddk demo` offers it on a terminal, and `ddk run` stops before any
  model call when the browser cannot start. `python -m ddk` works.
- **English and Korean.** Every message goes through `ddk.i18n`; English is the default, Korean when
  the locale is Korean, and `DDK_LANG=en|ko` overrides.
- README and user guide in English and Korean, `scripts/make_readme_assets.py` (rebuilds the
  pictures from a real demo run), and an Auto-fix Rulebook section for the implemented rules.

#### Claude 5 support
- `ddk.adapters.llm.model_traits` — one table of what each Claude model accepts and costs:
  `temperature` is sent only to models that take it, `effort` only where supported, and
  `claude-fable-5-1` / `claude-opus-5-5` / `claude-sonnet-5-5` (which reject a forced
  `tool_choice`) are asked to call the output tool instead; JSON written as plain text is
  accepted too. Unknown models get only universally accepted settings and the highest price.
- `LLMCallConfig.effort` (`low` … `max`) is passed as `output_config.effort`; it is part of
  the recorded request digest only when set, so earlier recordings keep their digest.
- Models that think by default get room for thinking on top of `max_tokens`; replies are
  streamed so long answers do not hit the read timeout; `refusal` is a clear error and
  `model_context_window_exceeded` counts as truncation; an unknown model ID names the
  `DDK_LLM_MODEL` setting in the error.
- Prices follow the 2026-10-14 price list, including Haiku 5.5's higher rate for prompts
  over 100,000 tokens.

#### Proof Program — executable Claim Gate
- `ddk proof` — verifies the GSD-superset capability matrix against real on-disk
  evidence and prints which claims (identity / parity / superset / superiority)
  are currently *allowed*, with explicit reasons. Supports `--json` and `--strict`.
- `ddk.models.proof` — `EvidenceRef`, `CapabilityFamily` (evidence-derived state),
  `ClaimGateResult`, `ProofReport` (Pydantic, `extra="forbid"`).
- `ddk.services.proof_ledger` — `ProofLedger` (matrix loader + evidence resolver)
  and `ClaimGate` (doc 27 / doc 28 gate rules). Mechanically **refuses superiority
  claims** until a calibrated `benchmarks/gsd-baseline.json` and a comparative
  artifact exist — the anti-overclaim guarantee.
- `benchmarks/capability-matrix.json` — machine-readable source of truth for the
  GSD-superset matrix (replaces the hand-maintained status column in doc 28).
- `benchmarks/gsd-baseline.json` — uncalibrated baseline template (superiority gated off).
- Filesystem resolution yields `mapped`, not `proved`; parity and superset remain
  denied until separate behavior-verification receipts exist.

#### Standards Compliance Auditor — clause-to-artifact coverage
- `ddk audit` — maps recognized standard clauses (ISO/IEC/IEEE 42010, ISO/IEC 25010,
  ISO/IEC/IEEE 12207, NIST AI RMF) to declared design artifacts and reports mapping
  coverage (`mapped` / `partial` / `gap`). `--json`,
  `--write` (emits `benchmarks/compliance-matrix.json`), `--strict`.
- `ddk.models.compliance` (`StandardClause`, `ComplianceReport`) +
  `ddk.services.compliance_auditor` (`ComplianceAuditor`) +
  `benchmarks/standards-catalog.json` (curated clause catalog, editable SSoT).
- This is an internal clause-to-artifact map, not certification or conformance.
  Artifact presence does not prove a normative requirement is satisfied.
- 18 new tests including a live-catalog audit that asserts real gaps are surfaced.

#### Operator Authority — explicit release/claim sign-off
- `ddk.models.operator` (`Operator`, `AuthorityScope`, `ApprovalRecord`,
  `AuthorityDecision`) + `ddk.services.operator_authority`
  (`OperatorRegistry`, `AuthorityController`).
- Enforces three process-local governance invariants on top of the Claim Gate: **scope grant**,
  **segregation of duties** (no self-approval), and an **architect floor** for
  superiority claims. Approvals append to an in-memory ledger; `record_approval`
  refuses to mint sign-off unless authority holds (`UnauthorizedApprovalError`).
- Durable audit storage is not implemented and is not claimed.
- 14 new tests covering scope/SoD/architect-floor authority and the approval ledger.

### Hardened
- **Repository path containment:** generated paths are canonical repo-relative paths;
  traversal, absolute/drive/UNC paths, and symlink crossings are rejected at both
  model and write boundaries.
- **Current model policy:** defaults are `claude-sonnet-5-5` and `claude-haiku-5-5`;
  config values propagate through graph services. The Claude adapter reads each model's
  request rules from `ddk.adapters.llm.model_traits` (see "Claude 5 support" below).
- **Honest assurance semantics:** artifact existence is `mapped`, never automatic
  behavioral proof; standards output likewise reports mapping rather than satisfaction.
- **Dependency security floor:** direct dependency minima and `uv.lock` were refreshed
  to versions passing `pip-audit` on 2026-07-27. Refreshed again on 2026-10-14 after the audit
  reported 41 advisories in the old pins: cryptography 50.0.2, gitpython 3.2.0 (minimum now
  3.1.60), langgraph-sdk 0.4.7, pyjwt 2.15.1, urllib3 2.8.0; the audit is clean and the suite passes.
- **Fail-closed release gate:** image-based cases cannot receive `ready` or a perfect
  precision score when visual regression evidence is missing.
- **Truthful sandbox selection:** the implemented `tempdir` runtime is now the default;
  unimplemented modes fail preflight instead of being silently replaced.
- **Subprocess secret boundary:** build commands now use an allowlisted environment,
  sandbox-local `HOME`/npm cache, and command validation; external symlink targets are
  excluded from the temporary repository copy.
- **Secret leakage to the LLM closed** (P0): `ContextPackBuilder` now excludes secret
  files (`security/secret_paths.py`: `.env`, `*.pem`, `*.key`, `.aws/`, `.ssh/`, …) and
  redacts inline credentials (`redact_string`) before any prompt leaves the machine.
  Previously it shipped `.env` and private keys verbatim to the provider.
- **LLM provider boundary** mapped to a typed `LLMError` hierarchy
  (`LLMAuthenticationError`, `LLMConnectionError`, `LLMRateLimitError`,
  `LLMResponseError`) — opaque SDK crashes become actionable failures. Added a
  configurable 120s call timeout and a guard so `complete_structured` raises instead
  of silently returning `"{}"` when the model emits no tool block.
- **Robust LLM JSON parsing** (`adapters/llm/parsing.py`): tolerates ```json fences and
  surrounding prose, so valid generations are no longer silently discarded by
  `code_generator` / `output_normalizer` (they used to fall back to empty output).
- **`ddk run` fails fast**: provider, API key, and input-image existence are validated
  *before* any workspace/case directory is created — no orphaned dirs on a doomed run.
- 30 new tests across secret-path detection, context-pack redaction, LLM error mapping,
  JSON parsing, and run preflight.

### Changed
- Playwright is a core dependency (`playwright>=1.49`); the `visual` extra is gone. The browser itself
  is still a separate download, or an installed Chrome.
- `ddk` is a package (`src/ddk/cli/`) instead of one module; behaviour of the existing commands is
  unchanged apart from the points above.
- The package description and the `Documentation` link describe the current tool.
- `CONTRIBUTING.md` and `SECURITY.md` point at `dogskip/ddal-ggak` and list the real quality gates.

### Removed
- Options and settings that did nothing: `--case-dir`, the global `--dry-run`, and the
  `pixel_diff_threshold` and `case_dir` settings.

### Fixed
- `_print_json` no longer corrupts large `--json` payloads (Rich `markup=False` +
  `soft_wrap=True` prevent `[..]` markup interpretation and hard-wrapping).
- `generate_node` replaced `assert`-based state guards with explicit `RuntimeError`
  raises so guards survive `python -O`.

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

[1.0.0]: https://github.com/dogskip/ddal-ggak/releases/tag/v1.0.0

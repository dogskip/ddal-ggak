---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: Phase 7 verified — self-checking loop complete
stopped_at: Phase 7 validation recorded (07-VALIDATION.md)
last_updated: "2026-10-14T04:54:20+09:00"
progress:
  total_phases: 7
  completed_phases: 7
  total_plans: 24
  completed_plans: 24
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-27)

**Core value:** Evidence-gated delivery — 증거 없이는 어떤 코드도 "완성"으로 인정하지 않는다.
**Current focus:** v1.2 self-checking loop verified; remaining gaps are listed in 07-VALIDATION.md

## Current Position

Phase: 07 (self-checking-loop) — VERIFIED ✅ (residual risk recorded)

## Performance Metrics

**Velocity:**

- Total plans completed: 24
- Average duration: —
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 3m33s | 2 tasks | 22 files |
| Phase 01 P04 | 2m29s | 2 tasks | 10 files |
| Phase 01 P03 | 3m03s | 2 tasks | 11 files |
| Phase 01 P02 | 5m18s | 3 tasks | 12 files |
| Phase 02 P01 | 8m | 3 tasks | 21 files |
| Phase 02 P02 | 13m | 2 tasks | 6 files |
| Phase 02 P03 | 685s | 2 tasks | 6 files |
| Phase 02 P04 | 22min | 2 tasks | 5 files |
| Phase 02 P05 | 15 | 2 tasks | 3 files |
| Phase 03 P00 | 3m | 2 tasks | 4 files |
| Phase 03 P01 | 10 | 2 tasks | 3 files |
| Phase 03 P02 | 8 | 2 tasks | 3 files |
| Phase 03 P03 | 198s | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 5-phase structure following import dependency chain (models → adapters → services → nodes → CLI)
- [Roadmap]: Phase 1 pulls INGEST-01, VALID-06, CERT-04, CERT-05 from other categories — architecturally these are foundation (workspace, policy, metadata schemas, preflight)
- [Roadmap]: Phase 4 is highest-risk — Playwright + worktree + auto-fix + retry loops converge
- [Phase 1]: D-01 — LangGraph context_schema + Runtime[ServiceContainer] DI 채택 (.from_config() 대신)
- [Phase 1]: D-02 — 40+ Pydantic 모델 전부 Phase 1에서 구현
- [Phase 1]: D-03 — Bottom-up TDD (모델→Protocol→Fake→DI→서비스→CLI)
- [Phase 1]: D-04 — 하이브리드 Git 연동 (읽기: GitPython, 쓰기: subprocess)
- [Phase 01]: Used StrEnum instead of (str, Enum) for Python 3.12+ — Ruff UP042 compliance
- [Phase 01]: Used datetime.UTC alias — Ruff UP017 compliance for Python 3.11+
- [Phase 01]: Used dataclass (not Pydantic) for Protocol supporting types — lightweight DTOs
- [Phase 01]: ENV_WHITELIST as frozenset — immutable security policy constants
- [Phase 01]: FAILURE_TAXONOMY with 19 entries covering build/type/lint/runtime/visual/data/async categories
- [Phase 01]: LLMCallRecord includes success + error_message fields beyond CERT-04 minimum for operational completeness
- [Phase 01]: 19 Pydantic models follow 12-data-models.md exactly — field names match design doc, not plan paraphrase
- [Phase 02]: TYPE_CHECKING imports in context.py to avoid circular imports for service type hints
- [Phase 02]: GenerationNode replaced task_description/output_files with node_type/target_path/validation_hooks/repair_hooks per 12-data-models.md
- [Phase 02]: D-05 enforced: thin adapter nodes for intake and repo_scan
- [Phase 02]: D-07 enforced: LLM haiku only when framework=other (static-first repo scan)
- [Phase 02]: FakeLLMAdapter key collision prevention: 'you' (SemanticIntentExtractor) vs 'analyze' (DesignSystemInferencer)
- [Phase 02]: enrich_profile() uses model_copy(update=...) for immutable RepoProfile updates — no Pydantic mutation
- [Phase 02]: Historical D-06 model choice was superseded in Phase 06 by config-injected
  `claude-sonnet-4-6`.
- [Phase 02]: ContextPackBuilder sort_key=(priority_rank,relation_rank,ceil(lines/50),normalized_path) per 24-context-pack-determinism.md §3.2
- [Phase 02]: Use Optional[RunnableConfig] in node_wrapper (not RunnableConfig | None) for LangGraph KWARGS_CONFIG_KEYS compatibility
- [Phase 02]: node_wrapper bridges LangGraph config injection to node kwargs via CONFIG_KEY_RUNTIME context extraction
- [Phase 03]: Additive-only model extension: all new fields have defaults, zero breaking changes
- [Phase 03]: float() cast in compute_drift_score: sum([]) returns int 0 — explicit cast ensures float return type contract
- [Phase 03]: System prompt 'Generate' → FakeLLM key=generate; node-by-node LLM calls.
  The historical Claude 3.5 default was superseded in Phase 06.
- [Phase 03]: LLM-based (haiku) normalization — NOT rule-based AST, per 16-prompt-design.md §6
- [Phase 03]: D-08 Phase 3 completion: 7-node graph replacing plan→END with plan→generate→normalize→END
- [Phase 04]: GraphState public contract is now 22 fields including failure_hash_history
- [Phase 04]: node_wrapper must support both direct runtime.context injection and config['configurable']['__pregel_runtime'].context fallback
- [Phase 04]: Playwright/SSIM integration tests remain opt-in with pytest marker; default regression uses -m 'not playwright'
- [Post-v1.0]: Visual regression path aligned to Pillow-only LocalScreenshotDiffAdapter; `scikit-image` removed from runtime dependencies and Chromium-backed Playwright integration validated
- [Post-v1.0]: MCP server tool surface (`design_new`, `preflight`, `ddk_version`), installer registration, slash-command templates, and `ddk serve/install` CLI flows are now regression-covered
- [Phase 06]: Untrusted generated/evidence paths use one repo-relative containment boundary;
  absolute, parent traversal, Windows drive/UNC, and symlink traversal are rejected.
- [Phase 06]: Artifact existence means `mapped`, never behavioral `proved`; parity, superset,
  and superiority remain denied until commit-bound verification receipts exist.
- [Phase 06]: Image-input releases fail closed when visual evidence is absent.
- [Phase 06]: Anthropic is the only implemented runtime provider; OpenAI/fake enum values are reserved.
- [Phase 07]: The visual gate uses Pillow only (grayscale 8×8 block SSIM + mismatch share); missing
  browser, preview server or evidence is `blocked`, waived only by `--no-visual`.
- [Phase 07]: Browser lookup order is `DDK_CHROMIUM_PATH`, Playwright's headless shell, then an installed
  Chrome/Chromium/Edge; availability is decided by a real launch (`probe`), not by a file check.
- [Phase 07]: `ddk demo` replays a recorded model reply and runs everything else for real.
- [Phase 07]: Each repair attempt gets a git checkpoint ref; going back is the user's `ddk rollback`, never automatic.
- [Phase 07]: The CLI speaks English unless `DDK_LANG` or the locale says Korean.
- [Phase 07]: Launch material is documentation only (`docs/launch/`); nothing is posted or published.

### Pending Todos

- Run `ddk run` with a live Anthropic key on at least three real designs and add the good and bad cases to the README
- Push the repository, then check the `uvx --from git+…` line, the new CI jobs and the social preview image
- Configure the PyPI trusted publisher and the `pypi` environment for `release.yml`
- Expose the image-to-code loop through MCP (today only Design Studio tools exist)
- Automatic rollback on failure, git worktree isolation, sandbox readiness in `ddk doctor`
- Commit-bound behavioral receipts and calibrated comparative benchmark corpus
- Replayable EvidencePack and durable operator approval ledger

### Blockers/Concerns

- Browser-backed tests ran for real on 2026-10-14 (7 passed); the model replies in them are recorded.
- Live Anthropic API behavior/cost was not exercised because no external credential was used.
- The new CI jobs (`package`, `e2e`) and `release.yml` were never run on GitHub Actions.
- `LICENSE` names `bjchoi` as the holder by assumption.
- `TempDirSandbox` filters subprocess environment and external symlinks but does not
  provide host filesystem, network, or CPU/memory isolation for malicious package scripts.
- Proof maturity is intentionally P-0: 14/14 mapped, 0/14 behavior-proved.
- Standards output is a mapping audit only: 13/16 mapped, 1 partial, 2 gaps.
- SSIM threshold 0.92 and comparative score thresholds remain uncalibrated.

## Session Continuity

Last session: 2026-10-14
Stopped at: Phase 07 implementation and validation recorded; nothing committed or pushed
Resume file: None

# Harness migration execution record

Base: `9a7832e`. Started 2026-10-18 (Asia/Seoul). Work is local on
`feat/harness-p0`; P1 follows on `feat/harness-p1` only after P0 checks pass.
No push, release tag, package publication, repository setting change, issue or PR is authorized.
The protected paths `ddal-ggak-clean/`, `.planning/`, `docs/design/` and `evidence/`
are excluded from inspection and modification.

## Common gate (G0)

Each stage commit requires all of the following on its final source:

```bash
uv sync --frozen --extra dev
uv run ruff check src/ tests/ scripts/
uv run ruff format --check src/ tests/ scripts/
uv run mypy src/ddk
uv run pyright src/
uv run pytest -m "not playwright and not docker and not integration" -q
```

Browser, Docker, real-provider effectiveness and remote Actions results are separate evidence.
Logs for this execution are under `/tmp/ddk-harness-work/`; a log is not remote CI evidence.
An intentional failing counterexample is recorded separately from stage acceptance.
The pre-change ordinary test suite passed 2,496 tests (72 deselected) on macOS ARM64.

## Stage results

| Stage | Commit | Gate evidence | Remaining risk | Approval needed |
| --- | --- | --- | --- | --- |
| P2 browser Cases | This change, `feat(bench): seal reviewed browser cases for pinned sources` | 58 focused checks; 9 actual-source browser decisions and 9 viewport checks; full G0 and package checks below | No model comparison, reviewed measurement or calibration ingestion | Approve the three draft hashes, execution host/model and budget before a measured episode |
| P2-1 | `a6749d2` | G0 all six commands passed on macOS and Linux: 2,579 ordinary tests each. Fixed 3-source preparation: 18 fresh contexts/hash matches; independent oracle: 9 source states / 27 checks with 6 expected counterexample failures. Sixteen paired-record tests passed | At this checkpoint, native Case compilation was manual; calibration ingestion remains absent | Approve criteria, host/model and spend ceiling before any paid comparison |
| P2-2 | `a6749d2` | Fourteen cost/privacy/unknown/integrity tests passed; 27 JSON routes and 37 CLI routes; all source modules referenced | Per-record observations, not invoice settlement or a global atomic snapshot | None |
| P1-1 | `584aaeb` | 35 command routes / 25 JSON routes; old-name warnings and separate case-path/ID options; all-command English/Korean help checks | Preflight now follows doctor's optional-provider warning; unsupported legacy runtime settings still block | None |
| P1-2 | `584aaeb` | Six precedence/origin/privacy checks and existing settings diagnostics passed | Listed application settings only; provider charging still needs explicit grants | None |
| P1-3 | `584aaeb` | Import-reference check: 167 modules / 0 unreferenced; nine removed modules / 466 source lines (four requested plus five newly unreachable model dependencies) | Literal dynamic imports are covered; arbitrary computed imports require review | None |
| P1-4 | `584aaeb` | Generated commands, exits, support tables and Claude adapters current; five guide pairs have matching structures and command sets | Parity is structural, not a semantic translation audit | None |
| P1-5 | `584aaeb` | Fourteen canonical MCP tools plus two aliases; 54 contract/server/real-stdio tests passed with MCP 1.30.0 | SDK/client coverage is bounded to tested revisions | None |
| P1-6 | `584aaeb` | Claude 2.1.302 strict validator: 0 errors / 0 warnings; native control initialization lists `/ddk:verify`; three skills, one Stop hook and MCP | Discovery does not prove model obedience; no paid prompt was sent | None |
| P1-7 | `584aaeb` | No known dependency vulnerabilities after removing the obsolete ignore and upgrading MCP; public-copy CLI reports two stable identity-refusal codes | Local unpublished DDK distribution itself is skipped by pip-audit | None |
| P0-5 | `54758af` | G5: wheel/sdist asset/privacy checks passed; clean environment printed `ddk 2.0.0` with both version interfaces; 25 focused tests passed. G0: all six commands passed; 2,588 passed / 72 deselected | Release is prepared locally; distribution checks are not runtime acceptance | Tag, push and PyPI publication |
| P0-4 | `ef66c46` | G0 passed on macOS ARM64 / Python 3.12.12 and Linux aarch64 container / Python 3.12.3: 2,564 passed, 72 deselected on each. G4: actionlint 1.7.12 passed; 37 focused tests passed; same-byte/reused-identity counterexample failed before the fix | One open reference per permitted source file; exhaustion blocks capture. Separate Linux host and Python 3.13 runtime evidence remain open | Remote CI run after an approved push |
| P0-3 | `8dde8c2` | G3: 23 CLI routes with success/usage-error coverage; 14 MCP tool contracts; real stdio checks. G0: all six commands passed; pytest 2,560 passed / 72 deselected | Public response boundary is breaking; canonical bytes retained | None |
| P0-2 | `17ae99a` | G2: three skills; all five CLI examples match the command tree; 29 focused tests passed including a recorded-response CLI dry plan. G0: all six commands passed; pytest 2,521 passed / 72 deselected | Recorded replies do not establish agent obedience or paid-model effectiveness | None |
| P0-1 | `4b76756` | G1: 33 focused installation/hook tests passed; Agent Skills rules checked in tests; generated README tables current. G0: all six commands passed; Ruff 406 files, mypy 175 source files, Pyright 0 errors; pytest 2,518 passed / 72 deselected | Interactive host loading remains unverified | None for local implementation |

## Host decisions and official sources

The installation registry is the authority for generated README support tables.
The following official documents were consulted on 2026-10-18. They establish configuration
formats, not evidence that every host application loaded a generated file.

- [Agent Skills specification](https://agentskills.io/specification): canonical name/description and directory contract.
- [Claude skills](https://code.claude.com/docs/en/skills) and [MCP](https://code.claude.com/docs/en/mcp): `.claude/skills/`, project `.mcp.json`; global MCP is an owner action, never a direct edit to `~/.claude.json`.
- [Gemini commands](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/custom-commands.md): project/user `.toml` commands with `prompt` and optional `description`.
- [OpenCode commands](https://opencode.ai/docs/commands/) and [MCP](https://opencode.ai/docs/mcp-servers/): project `.opencode/commands`, global `.config/opencode/commands`, direct `mcp.ddk` local command array.
- [Codex skills](https://developers.openai.com/codex/skills) and [MCP](https://developers.openai.com/codex/mcp): `.agents/skills/`, `[mcp_servers.ddk]`; project configuration is effective only in a trusted project. Installation does not grant trust.
- [Copilot prompt files](https://code.visualstudio.com/docs/copilot/customization/prompt-files): `.github/prompts/*.prompt.md`; global storage depends on the selected VS Code user profile and is not guessed.
- [Cursor rules](https://cursor.com/docs/context/rules) and [MCP](https://cursor.com/docs/context/mcp): project `.mdc`, `.cursor/mcp.json`; global rule settings are not a documented installable file target here.
- [Kiro steering](https://kiro.dev/docs/steering/): project/global `.kiro/steering`, manual inclusion.

## Unverified decisions

| Item | Boundary |
| --- | --- |
| Live host sessions | File/configuration tests do not prove command discovery by an installed host. |
| Global Copilot/Cursor rules | Unsupported; project scope or an owner-maintained AGENTS.md is the fallback. |
| Provider benefit | No paid provider invocation or inferred improvement percentage. |
| Remote CI and publication | No remote mutation; later approval is required. |

## Response contract verification

The CLI has 23 JSON-capable routes after adding installation previews and removal.
All 23 were observed returning a successful public envelope through real CLI callbacks in
temporary repositories; service fixtures supply synthetic ready results where execution would
otherwise require a provider, browser or sealed case. Every route also rejects a bad option as
a single JSON usage-error envelope. This establishes the response boundary, not acceptance
for a synthetic ready run. All 14 MCP tools have success/input-rejection contract coverage;
existing owner-grant and real stdio tests remain in place.

`verified-change/1` on disk is retained; public callers read canonical records under `data`.
Saved blocked decisions retain their actions. Input/environment action categories come from an
explicit registry; unknown actions cannot upgrade a blocked result. A replay or current-source
failure exits 5. Empty legacy status exits 1 with `case_not_found`.

## Cross-platform evidence and remote checks

The reported original pair of Linux failures was not reproduced: the six selected baseline tests
passed. The new source-capture counterexample simulates reused identity/timestamps and fails
without retained references. Replacement remains forbidden, including equal bytes/mode.

The first Linux dependency bootstrap could not resolve an uncached isolated build dependency
without network access. A later full run exposed eight process-lifecycle failures in a container
whose PID 1 was Python: `ps` showed defunct Node children owned by PID 1. With Docker `--init`,
the same source passed all 13 process-lifecycle tests and then all 2,564 ordinary tests.
The passing environment uses `ddk-harness-check:20261018`
(`sha256:6ca3e7546df35bcfd831bb61356f717fd58e5f236ed163e4bb8eec823f6f106b`).
Source export included only public tracked files and task-owned source/test/script additions.
The source hashes are recorded in `/tmp/ddk-harness-work/linux-p0-4-sha256.json`.

No GitHub settings were changed. Before calling remote CI healthy, inspect Actions permission,
workflow enablement, event/branch filters, fork/token permissions and required branch checks.
After an approved push, the exact HEAD must have a run with all four OS/Python combinations
successful. Local Linux container results are not that remote result.

## Prepared 2.0.0 release

The package version, installed metadata and eager `ddk --version` interface are 2.0.0;
`ddk version` remains available. The changelog groups the breaking response and installation
changes under 2026-10-18. This is a local release preparation, not a published release.

Builds use a public source export so protected directories are not traversed or copied.
The wheel/source checks include all three skills and their references. A public skill named
`ddk-evidence` must not be confused with a private `evidence/` directory: archive checks match
path components. All 22 root/nested private-path counterexamples stay rejected.
The clean virtual environment installation uses the frozen runtime dependency constraints.

The following release actions are prepared for review and have **not** been executed:

```bash
git tag v2.0.0
git push origin v2.0.0
```

They require user approval. The existing `release.yml` uses Trusted Publishing after tag/version
agreement. The owner must first verify the PyPI publisher and GitHub `pypi` environment, review
artifacts and confirm the exact HEAD's remote CI results. No tag or package publication is part
of this local execution.

## P1 implementation boundaries

Work continues on `feat/harness-p1` after all five P0 stage commits passed G0.
The protected paths remain excluded. The source reference check found the four requested
unused modules; removing `design_package` made its five model-only dependencies unreachable.
Those five types and only their dedicated serialization tests were also removed. No active
security or runtime acceptance test was weakened. Public capability references now point to
current acceptance compilation, runtime scorecard and canonical record storage.

The configuration order is explicit option > environment > repository `.env` > `ddk.toml`
`[settings]` > default. Source aliases are normalized before merging; a plain API-key environment
variable therefore beats a prefixed key in a lower-priority file. Inspection masks credentials.

The five public guide pairs have section, fenced-example and actual-command parity checks.
Command/exit/support references and Claude adapters have deterministic regeneration checks.
The native Claude 2.1.302 loader prioritizes a source skill's `name` over a manifest command-map
key. A canonical source file therefore produced `/ddk:ddk-verify` in the first loader probe.
The generated manifest command map omits source frontmatter names and binds the canonical
bodies/references. This avoids duplicate skill assets and preserves private-directory exclusions. Native initialization now exposes `/ddk:design`, `/ddk:evidence`, `/ddk:verify`.
The probe sent one initialize control request and **zero user messages**. It establishes native
command discovery, not model compliance or paid-model effectiveness. Native strict manifest
validation and component inventory also passed. Other host runtime discovery is unverified.

Official sources: [plugin manifest](https://code.claude.com/docs/en/plugins-reference),
[marketplace](https://code.claude.com/docs/en/plugin-marketplaces),
[SDK initialize protocol](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/query.py).

An audit without exceptions found MCP 1.28.1 / CVE-2026-59951. The
[upstream advisory](https://github.com/modelcontextprotocol/python-sdk/security/advisories/GHSA-84m7-p3x7-pcfv)
excludes stdio-only servers. The minimum and lock were still advanced to fixed MCP 1.30.0;
DDK's transport is not represented as affected. Pygments was already fixed at 2.20.0,
so its obsolete ignore was removed. Remote Actions settings and execution remain unverified.
Feature-branch push filters and manual dispatch are prepared locally, without publishing.

P1 acceptance: `/tmp/ddk-harness-work/p1-final-g0.json` records all six G0 exits as 0;
2,540 ordinary tests passed, 72 were deselected. The focused run passed 414 tests.
The first full attempt failed nine stale-name/diagnostic assertions and exposed missing
unsupported-runtime checks plus an incomplete translated authority warning. The final change
restores explicit host-permission/no-OS-isolation disclosure and checks unsupported providers,
SDK availability and sandbox modes in doctor. Invalid settings are still checked before run I/O;
the tests use that canonical diagnostic path. Optional provider credentials warn because pure
verification does not require a model. No execution grant is inferred from that warning.

## P2 preparation and local reporting

`ddk bench` reads strict paired host/oracle/gate records. It checks cohort, initial/request/source
hashes, unique sessions, artifact integrity and completed canonical gate records, retaining failed
and incomplete observations. Its input provenance is declarative: changing that label cannot promote
records into reviewed measurements or calibrated claims. The published baseline remains unchanged
with `calibrated: false`; model comparisons and review-to-calibration ingestion remain unexecuted.
See [the protocol](../benchmarks/PAIRING.md) and [Korean protocol](../benchmarks/PAIRING.ko.md).

The three pinned sources were fetched read-only into task-owned temporary clones. Preparation
created 18 independent contexts and local `bench-source` baseline commits. Native oracle checks
covered original, controlled-broken and manually restored source states for all three projects.
The physical results are in `/tmp/ddk-harness-work/oracle-matrix/summary.json`. These are preparation
and oracle checks, with zero product model calls; they are not a repair-effectiveness experiment or
DDK acceptance of three independent production repositories. At this checkpoint, browser-oriented
bootstrap did not compile these native tasks. The browser Case follow-up below addresses that gap
without relaxing the acceptance contract.

`ddk stats` uses bounded, read-only metadata access and the existing canonical record/price/usage
validation. It exposes numeric aggregates only. Missing or unsettled cost stays null, unknown
legacy error charges are not zero, and corruption, duplicated calls, links and excessive input
are rejected. Completed canonical records take precedence over pending copies. It neither settles
invoices nor provides an atomic snapshot across all changing records.

P2 focused acceptance: 294 tests passed, including 14 local-stat checks, 16 paired-record checks,
execution-grant/output-preservation checks, all-command language coverage and regenerated references.
Static checks currently pass for 170 source modules; the import-reference check reports 0 unused.
The public tree has 37 command routes, 27 accepting JSON. No network telemetry, provider call,
remote publication, tag or repository setting change was performed.

The final archive check found that a generated public plugin directory named `evidence/` collided
with the unchanged private-material exclusion. The fix renders the same three canonical bodies
as documented inline manifest command aliases alongside the three canonical skills instead. No exclusion or security counterexample was relaxed.
Native loading and distribution validation are repeated for this final representation.

## Local acceptance at a6749d2

The `a6749d2` source passed every G0 command on macOS ARM64 / Python 3.12.12 and the
Linux aarch64 / Python 3.12.3 test container. Each ordinary run passed **2,579** tests
with 72 deliberately excluded. All 72 were exercised separately from macOS: **47**
headless end-to-end tests, **5** headless integration tests and **20** Docker tests
passed with no skips among selected tests. These sets cover all 2,651 collected tests.
Docker tests include the nine isolated repository reproduction variants; their coordinator
is macOS, so this is not a native Linux run of every browser test.

```sh
DDK_E2E=1 uv run pytest tests/e2e -m 'playwright and not docker' -q --tb=short
DDK_E2E=1 uv run pytest tests/integration -m playwright -q --tb=short
# Existing immutable app/checker image IDs were supplied for this command.
DDK_E2E=1 DDK_DOCKER_E2E=1 uv run pytest tests/e2e -m docker -q --tb=short
```

Receipts: `/tmp/ddk-harness-work/p2-accepted-g0.json`,
`/tmp/ddk-harness-work/p2-linux-final/g0.json` and `final-test-receipts.json`.
The final source export's per-file hashes are in `final-public-r2-sha256.json`.
Actionlint passed. The audit reports no known dependency vulnerabilities, with the local
unpublished DDK distribution explicitly skipped. The four remote OS/Python CI combinations
remain unverified. Python 3.13.7 was used for the separate clean wheel installation smoke test,
not the full ordinary test suite.

Both wheel and source archive pass privacy/runtime checks. All **188** packaged runtime files
match that checkpoint's source bytes. A separate Python 3.13 environment prints `ddk 2.0.0` through
both version interfaces, loads all three corpus tasks, returns a valid empty `stats` envelope
without creating storage, and returns an unmeasured `bench` envelope with exit 1.
Native Claude strict validation has no errors/warnings; its three canonical skills and friendly
`/ddk:design`, `/ddk:evidence`, `/ddk:verify` aliases load from the local plugin. No user prompt
was sent. Other hosts' configuration formats have tests; their interactive discovery remains open.

The original browser doctor resolved a different global Python/Playwright version with a missing
browser. Running the same diagnostic with the project interpreter passed both headless DOM and
Playwright API checks. Existing binaries were reused; no browser was installed for this task.

Fresh, unmodified model-comparison inputs are retained separately from the manual oracle
counterexamples: `/tmp/ddk-harness-work/paired-contexts-unmeasured`. All 18 initial hashes were
rechecked. The macOS `/tmp` alias was resolved before that descriptor-based check; the earlier
alias-path rejection was not bypassed or weakened. These are the previous corpus inputs; the
follow-up below records the current unmeasured inputs. No repair success percentage is reported.

No push, tag, PyPI publication, issue/PR, remote setting change or paid product-model invocation
was executed. Protected source paths were excluded from agent inspection and modification.

## P2 browser Case follow-up

Preparation now creates three reviewable JSON drafts and identical browser fixture sources in
both arms. Target and preservation remain independent required browser checks. Each task permits
changes only to its original source file; changing the helper is outside scope. `seal` requires
three exact reviewed draft hashes and compiles one immutable Case per task, shared across the
three DDK trial directories. All plain directories remain free of DDK state. Neither command
grants candidate execution or provider spending. Criteria are in [the Case notes](../benchmarks/BROWSER-CASES.md).

Sealing validates all 18 directories before publishing Cases, including request hashes, duplicate
rows, path containment, fixture bytes and complete pinned upstream source hashes. A changed initial
tree cannot become valid by replacing the preparation's own hash declarations. Controlled mutation
reconstruction selects the original file by SHA-256 rather than assuming the changed text occurs
only once. Draft edits require their new reviewed hashes; unapproved drafts remain blocked.

Review also produced an independent failing counterexample: an inherited Git `post-commit` wrote
a canary while preparing temporary comparison repositories. Preparation now removes inherited
Git configuration variables, ignores global/system configuration and attributes, omits templates,
and disables hooks, filesystem monitors and signing for those new repositories only. The actual
project's Git configuration and commit checks are unchanged. The focused regression, Case and
distribution checks pass **58** tests, including **19** preparation/approval/fixture checks.

Browser fixture review passed nine task/viewport combinations (320, 768 and 1280 px), with no
horizontal overflow or browser console/page errors. Counter Add one and Reset changed actual
state; Tab, Shift+Tab, Enter and Space operated the controls, with visible focus and 44 px targets.
The fixed black/white colors have 21:1 contrast. Screenshots and DOM records are in
`/tmp/ddk-harness-work/p2-case-browser-review/summary.json`; Python empty/error/host-package
fallback cases are exercised by the focused test command.

Five additional headless checks observed JS loading, module failure and empty-result states using
explicitly controlled module responses. Those are fixture behavior checks, separate from the
actual pinned-source scenarios. The draft's per-rule UI check is in the Case notes.

The final source scenarios passed all nine expected decisions: manually restored candidates are
ready (3), original controlled defects are blocked (3), and restored targets with a preservation
regression are blocked (3). Every baseline preservation check passed, and each preservation
counterexample retained a passing candidate target. All nine completed records passed offline
replay integrity, current-source gate checks and cleanup checks. The independent oracle executed
27 checks with process exits preserved. No coding model was invoked.
Receipt: `/tmp/ddk-harness-work/p2-cases-hardened-engineering/engineering-summary.json`.

Fresh unmodified comparison inputs are in `/tmp/ddk-harness-work/p2-cases-hardened-unmeasured`.
All 18 initial hashes were checked again; none has a `.ddk` directory. The three complete drafts
and their exact hashes are in `review-packet.json`. This is still owner review material, not an
approved model experiment. The baseline remains `calibrated: false`.

All six G0 commands passed on the final code on macOS ARM64 / Python 3.12.12 and Linux aarch64 /
Python 3.12.3. Each ordinary suite passed **2,595** tests with 72 excluded, with no failures.
Receipts: `/tmp/ddk-harness-work/p2-cases-hardened-g0.json` and
`/tmp/ddk-harness-work/p2-cases-hardened-linux/g0.json`. The 2,667-test collection includes the
previously verified 72 browser/Docker/provider-marked tests; those full sets were not rerun in
this follow-up. The nine actual-source browser scenarios and nine viewport checks above are
new macOS observations, not Linux browser acceptance or a model-effectiveness experiment.

All four generated document checks passed. The surface still has 37 routes including three
groups (34 terminal commands), 27 JSON-capable commands and 170 referenced source modules.
The new public fixture makes 189 runtime files. Publication, paid model episodes and remote
CI remain unexecuted. No previously protected source or unrelated work was inspected or edited.

The wheel and source archive passed `scripts/check_wheel.py`. All 189 wheel runtime files match
the source bytes. A clean Python 3.13.7 installation passed both version interfaces, fixture/corpus
hash checks, empty read-only stats and an unmeasured bench response. Its preparation command also
created 18 fresh unapproved inputs using the installed package. This is a package smoke test,
not the full Python 3.13 suite. The package receipt is `/tmp/ddk-harness-work/p2-cases-package.json`.

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
| P0-5 | `chore(release)` stage commit | G5: wheel/sdist asset/privacy checks passed; clean environment printed `ddk 2.0.0` with both version interfaces; 25 focused tests passed. G0: all six commands passed; 2,588 passed / 72 deselected | Release is prepared locally; distribution checks are not runtime acceptance | Tag, push and PyPI publication |
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

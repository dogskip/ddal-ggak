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
| P0-3 | `feat(contract)!` stage commit | G3: 23 CLI routes with success/usage-error coverage; 14 MCP tool contracts; real stdio checks. G0: all six commands passed; pytest 2,560 passed / 72 deselected | Public response boundary is breaking; canonical bytes retained | None |
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

# One-command verified changes

[한국어](ONECLICK.ko.md) · [Full verification contract](VERIFIED-CHANGES.md) · [Catalog fields](CATALOG.md)

`ddk up` captures existing Git changes, verifies frozen acceptance checks, optionally repairs them,
exports review evidence and previews application. `--apply` explicitly requests managed application.
It does not invent acceptance tests from a prose request. Missing independent target and preservation
checks produce `acceptance_checks_required`, before project commands or model calls.

## First case without manual hashes

Run `ddk doctor --dry-run --json` to inspect Python, Git, Docker, installed image digests, Chromium,
fonts and provider availability. It does not install dependencies or call a model. `warning` can mean
an optional provider is absent or the working tree has changes; `blocked` means a required prerequisite
is unavailable. Tool inspection includes concrete next actions. Prepare dependencies separately.

Put reviewed behavior in `.ddk/verify.toml` (local), `ddk.toml`, or `[tool.ddk.verify]` in `pyproject.toml`,
in that precedence order. This example uses a static project whose Git base has a heading and a working
Continue link to `/next.html`. The candidate changes the heading to After and must preserve navigation:

```toml
preview_argv = ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
scope_paths = ["index.html"]

[[checks]]
check_id = "heading"
role = "target"
steps = [{action="expect-text", selector="h1", value="After"}]

[[checks]]
check_id = "navigation"
role = "preserve"
steps = [{action="click", selector="a"}, {action="expect-text", selector="h1", value="Next"}]
```

```bash
ddk up "Change heading and preserve navigation" --dry-run --json
ddk up "Change heading and preserve navigation" --trusted-local --json
```

`--trusted-local` grants execution of the project's commands with host permissions, in a private copy.
Automatic bootstrap currently records the observed host environment at this assurance. It never upgrades
that evidence to isolated assurance. Existing explicitly prepared isolated cases remain supported.
The compiler records source, criteria, execution plan, actual Chromium SHA-256, fonts, lockfiles,
manifests, existing Docker image digests, OS and Python. No manual digest assembly is required.
`ddk init --request "..."` and `ddk change init` create the same case without executing checks.
`--from-design design-package/` imports `manifest.json` requirements and an optional `verification.json`
with the same checks/configuration structure. Unmapped design requirements require review and block
acceptance; explicitly mapped `check_ids` are preserved.

Git extraction uses local object bytes and a bounded private snapshot; it does not switch branches,
reset the working tree, initialize submodules or execute filters. `--git-base HEAD~1` selects a base;
`ddk change verify --git-base REF` is also available. Physical baseline/candidate directories remain
supported. Source symlinks, hardlinks, submodules and ambiguous file states are rejected. Secret and
runtime paths are excluded by the existing source-path policy. Deleted files require an explicitly
linked requirement with `allow_delete=true` and an allowed path. Permissions remain protected.

## Repair and application

```bash
ddk up --case CASE_UUID --git-base HEAD --repair --confirm-provider --trusted-local --json
ddk up --case CASE_UUID --git-base HEAD --apply --trusted-local \
  --confirm-local-storage --confirm-quiescence --json
```

`up` checks without a model first. It constructs a provider only if repair actually needs a proposal.
Repair shares one durable time/output/call/cost budget and independently rechecks every proposal.
The default Anthropic price catalog is dated, expires after 30 days and requires `--price` after that;
other providers require an explicit case-bound quote. `--provider` accepts `anthropic`, `openai-compatible`,
`claude-cli` and `codex-cli`; compatible APIs also need `--endpoint`. CLI bridges disable personal
customizations and execution tools and use a private empty working directory. Their billing remains
unknown with the current CLI reply formats, so they stop without a ready verdict. Never treat a
subscription or a local endpoint as proof of zero cost. API usage missing cache/charge evidence also stops.
Supported CLI versions must recognize the restrictive options; unsupported versions fail closed.

A proposal is either a full-file replacement or exact, sequential search/replace patches:

```json
{"patches":[{"path":"index.html","hunks":[{"search":"Broken","replace":"Continue"}]}]}
```

Each search must occur exactly once. Empty/unchanged searches, duplicate paths, missing files,
ambiguous matches, invalid UTF-8, excessive size and out-of-scope changes stop the request.
Recent masked failure lessons and AX/visual diagnostic excerpts are advisory model context;
the catalog cannot grant a passing verdict. Repeated candidate hashes stop the current repair request.

The apply preview compares the sealed original candidate with the final candidate, including files
restored to the Git base and repairs of newly added files. Managed application checks exact bytes and
modes, backs up existing files and journals creates/updates/deletions. Concurrent or external edits
cause a conflict or explicit unknown recovery state and are preserved. Local storage and quiescence
confirmations are required. `--apply` uses the existing owned apply/recovery service.

## Native reports and policy

A test check selects `report_adapter`: `ddk-json`, `pytest-json`, `junit-xml`, `vitest-json`, `jest-json`
or `playwright-json`. Use `{report}` in `command_argv` for a runner-written report file in the owned
workspace/results directory, for example `python3 -m pytest --junitxml={report}`. With no placeholder,
stdout must be exactly the selected report. Runner exit failures cannot be overridden by a green report.
Missing, malformed, contradictory and zero-execution reports block. Skips block by default;
`allow_skipped=true` allows explicit platform skips, but still requires at least one executed test.
Flaky Playwright results remain failures. Native project tools/dependencies must already be available;
parsing a format does not establish every framework/version's execution support.

Policy definitions accept `forbidden_paths`, `forbid_secret_patterns`, `forbid_regex`,
`max_changed_files` and `max_changed_lines`. Globs are case-sensitive relative paths. Regex support
rejects groups/backreferences and multiple quantifiers rather than guessing intent. Text scans report
exact path/line/reason without the matched value. Limits inspect baseline-to-candidate changes;
changed-line count includes removed plus added lines. Host and isolated evaluators use the same trusted,
owned worker with a check/run deadline and bounded redacted evidence. This is a mechanical policy
check, not a general security audit or semantic proof of a request.

## Headless probe and accessibility

```bash
ddk probe --url http://127.0.0.1:3000 --viewport 1280x800 --out .ddk/probes/latest --json
ddk probe --url 'python3 -m http.server {port} --bind 127.0.0.1' --confirm-execution --json
```

Capture produces PNG, ARIA snapshot, DOM, console/page/network errors, optional selector bounds and a
cleanup receipt. Cross-origin requests and WebSockets are blocked. Chromium runs headless with its
sandbox enabled, fixed time, locale, timezone and viewport. Browser failures never become passing
observations. Fixed browser flows support `expect-ax-tree`, `expect-ax-role` and
`expect-no-console-error`; snapshots and failure cleanup retain AX evidence alongside RGB/SSIM data.

`--reference path.png` creates a pixel diff. To register a reference, use
`--case CASE_UUID --check CHECK_ID --update-reference references/page.png` (alias `--update-baseline`).
It requires a ready observation, matching environment/time/viewport, exact observed image hash and a
new reference path. The command creates a **new superseding case**, preserving the original criteria.
Selector crops remain selector crops. A failed check cannot silently replace its own acceptance image.

## Catalog and MCP

Canonical files keep their existing paths under `.ddk/verified-change/1/`: `cases/<id>/case.json`,
`runs/<id>/run.json`, and `applies/<id>/apply.json`, with frozen inputs and evidence beside them.
`index.sqlite3` is a disposable SQLite/FTS5 projection, synchronized after canonical writes.
`ddk change reindex` validates JSON and evidence, rebuilds all rows privately and atomically replaces
the catalog. Rebuild equality means equal normalized rows and query results, not equal SQLite/WAL bytes.
An index failure cannot undo a canonical save; a warning requests reindexing. Historical lookup failure
only omits advisory history. The [catalog reference](CATALOG.md) lists all twelve tables and columns.

`ddk serve` exposes eight verified-change tools: `ddk_doctor`, `ddk_init`, `ddk_verify`, `ddk_repair`,
`ddk_status`, `ddk_probe`, `ddk_apply`, `ddk_query_ledger`, plus existing design/preflight/version tools.
Extra properties, invalid types and raw stdio frames over 2 MiB are rejected. Verification remains
isolated-only. Mutating/provider/probe operations require both a server-owner capability and per-call
`approved=true`: configure `DDK_MCP_REPOSITORY` to the exact repository and `DDK_MCP_CAPABILITIES` as a
comma-separated subset of `init,repair,probe,apply,trusted-local`. Default is no such grants.
`trusted_local=true` additionally requires the owner `trusted-local` grant. Compatible API repair
also requires an exact `DDK_MCP_PROVIDER_ENDPOINT` owner setting, preventing a caller from redirecting
the configured API credential to another endpoint. Ledger queries select only
safe metadata columns in SQL, never arbitrary SQL, source, raw requests or diagnostic logs.

A ready result proves the frozen required checks and integrity/cleanup/cost conditions for that run.
It does not establish defect-free software, paid-model repair effectiveness, independent adoption or
superiority over another harness. See the [roadmap](../ROADMAP.md) for the next evidence priorities.

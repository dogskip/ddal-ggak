# Verify existing changes and apply them safely

[한국어](VERIFIED-CHANGES.ko.md) · [Roadmap](../ROADMAP.md)

`ddk change` is separate from legacy `run`, `status`, `apply` and `demo`. Verification needs neither
a model nor an API key. Images are required only for visual criteria.

## Prepare the inputs

Supply an approved case, fixed inputs, explicit baseline and candidate directories, and a mapping
of changed paths to approved requirement IDs. With `case.json` beside `inputs/`, the input-directory
option can be omitted. The [JSON Schema](../src/ddk/assets/verified-change/contract.schema.json) and
[valid/invalid examples](../tests/fixtures/verified-change/contract-examples.json) define the records;
runtime semantic validation additionally checks their relationships.

The baseline must match fixed source/protected files in content and permissions. Candidate changes
may create or modify in-scope source files; deletion, relocation, permissions, tests, criteria and
dependency changes are rejected. `--project-inputs` maps protected project paths to fixed input paths;
`--change-requirements` maps changed paths to approved requirement-ID arrays. Nothing infers approval
or the Git baseline.

Fixed inputs include an Environment record and `criteria/execution.json`, itself a criteria input.
The plan accepts exactly these fields:

| Field | Meaning |
| --- | --- |
| `format` | `verified-evaluator/1` |
| `environment_path` | Relative path to the fixed Environment file |
| `criteria_paths` | All criteria files, including this plan |
| `environment_paths` | Environment file list |
| `preview_argv` | Command array; only a complete `{port}` argument is substituted; empty for command-only checks |
| `frozen_time` | Fixed timezone-aware ISO 8601 time |
| `browser_executable` | Absolute executable path or `null` for discovery |
| `visual_references` | Path, viewport, Environment-object SHA and `mask_sha256: null`; empty without visual checks |

Hashes, sizes and permissions are checked against actual files. The case environment hash identifies
the environment **file manifest**; a visual reference identifies the Environment **object**.

## Execution and assurance

Default `isolated` uses separate app and checker containers on a local Docker daemon with prebuilt
immutable images. Missing protection/runtime support gives `isolation_unavailable`. There is no image
pull, dependency installation or host fallback. Explicit `verify --trusted-local` runs trusted project
commands with user permissions and no OS isolation; the case must also request that assurance.
A stored case alone never grants execution, and an isolated case cannot be downgraded.

The app receives a writable source copy. The checker receives read-only criteria and writable results,
without source. They share a network namespace without external access, using internal port 4173 and
no published host port or Docker socket. Read-only system files, dropped capabilities, Chromium-compatible
seccomp and CPU/memory/process/time limits apply. Chromium is headless with its sandbox enabled.

The app image needs the fixed Node runtime and dependencies. The checker needs Python 3.12+,
Playwright, matching Chromium, Pillow, jsonschema and fontconfig; see the example
[Dockerfile](../tools/verified-checker/Dockerfile). Prepare images separately. Record each local
`docker image inspect` `Id` without `sha256:` in Environment. Tags and remote endpoints are rejected.

Runtime checks compare immutable image IDs, Docker ServerVersion, OS/architecture, Python, Node,
package-manager, Playwright and browser versions, browser executable SHA, font manifest, protected
lockfile bytes and isolation policy SHA. `ddk.adapters.verified_isolation.POLICY_SHA256` and
`ddk.adapters.verified_worker.font_manifest` define the policy/font calculations. Expectations are
never updated to match a run. Lockfile equality does not prove the image was built from that lockfile;
prepared dependencies remain a trusted input.

Docker logging is disabled. Attached output is bounded and charged cumulatively across baseline and
candidate. Missing, excessive or unknown accounting stops further checks. Cancellation/timeouts remove
only owned containers and verify their absence. Source-copy content, permissions and file lists are
checked after termination. Unconfirmed cleanup, evidence retrieval or integrity cannot yield `ready`.

The local daemon and checker image are trusted. Writable source copies have no separate disk quota;
this is not whole-host protection from malicious programs. Actual acceptance covers macOS ARM64,
OrbStack Linux and a static Node fixture. Other hosts and real Vite/Next.js projects need direct evidence.

`command` executes fixed `command_argv` without shell evaluation. `test` currently requires one JSON
object with integer `executed_count`, `failed_count`, `skipped_count`. Missing, malformed, zero-test
or skipped reports cannot pass. Project reports are identified as `project-report`, separate from
independent browser observations. Arbitrary Vitest/Jest formats and executable `policy` criteria are
not supported yet.

## Commands and results

Use `ddk change <command> --help` for complete options.

| Command | Main inputs | Behavior |
| --- | --- | --- |
| `verify` | `--case` or `--case-id`, `--baseline`, `--candidate`, optional `--run-id` and mappings | Check fixed criteria; `--case` also imports the definition |
| `status` | `--run-id` | Validate and inspect saved state; never restart work or create a repository |
| `export` | `--run-id`, new ZIP `--destination` | Export review JSON and permitted evidence without overwriting an existing archive |
| `apply` | Case/run IDs, run/change hashes, `--confirm-local-storage`, `--confirm-quiescence` | Managed apply of a ready result; default required assurance is isolated |
| `recover` | `--apply-id`, local-storage, same-host and quiescence confirmations | Recover interrupted work after its owner ends; compare current contents and preserve external changes |

`--repo` identifies record storage and the apply target. `--json` writes JSON only to stdout, with
diagnostics on stderr. Exit codes: ready 0; blocked/manual-review 1; invalid input/unavailable 2;
cancellation 130. An omitted run ID gets a UUID. The same ID and request reads saved state; different
inputs with the same ID conflict.

Default exports exclude sensitive originals, model responses, screenshots and logs.
`--include-sensitive` explicitly includes them and is not a public-sharing safety guarantee. Reports
contain verdict, assurance, checks, hashes and action codes without raw provider errors.

Export and apply are separate. Apply rechecks source existence, regular-file status, contents and
permissions. Uncertain state remains `unknown`. Forced overwrite and whole-repository reset are
unavailable; failed cleanup/persistence never becomes success. Recovery handles interrupted owned
transactions, not arbitrary undo of completed transactions or legacy image-run applies.

## MCP and current limits

`ddk serve` exposes `ddk_verify` and `ddk_status` alongside `design_new`, `preflight` and `ddk_version`.
They share CLI services/contracts/storage. Verification is isolated-only; apply, recovery, installation,
export and trusted-local grants are not exposed. Status reports stored assurance without upgrading it.

Required-check failure is a normal blocked result. Invalid input and unavailable execution are tool
errors; persisted run IDs remain inspectable. Testing covers SDK 1.28.1 and negotiated revision
2025-11-25, not every client or later revision. Tool annotations do not replace authorization; see the
[MCP tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Oversized, excessively nested, duplicate-key or invalid UTF-8 requests terminate stdio without
manufacturing successful replies or deleting saved runs.

Automatic repair/reverification, common test-report adapters and guided case preparation are unfinished.
The legacy demo uses recorded model responses; this path verifies explicit changes without a model.
Passing fixed criteria does not prove a defect-free app, product superiority or GitHub popularity.

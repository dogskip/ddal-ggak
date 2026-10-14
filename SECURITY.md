# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in ddalggak, please report it responsibly.

### How to Report

1. **Do NOT open a public GitHub issue** for security vulnerabilities.
2. Email the maintainers at the address listed in the project metadata, or use
   [GitHub Security Advisories](https://github.com/dogskip/ddal-ggak/security/advisories/new).
3. Include:
   - A description of the vulnerability
   - Steps to reproduce
   - Impact assessment
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment** within 48 hours of your report.
- **Initial assessment** within 5 business days.
- **Fix timeline** communicated once assessed — critical issues patched within 7 days.
- Credit in the changelog (unless you prefer to remain anonymous).

## Security Practices

### API Key Handling

- All API keys are loaded via `pydantic-settings` with `DDK_` prefix environment variables.
- Keys are **never** logged — `security/redact.py` scrubs 7 sensitive patterns from all log output.
- `.env` files are excluded from version control via `.gitignore`.
- The `.env.example` file contains placeholder values only.

### LLM Context Protection

Source code is sent to the LLM provider to generate/normalize code. Two defense layers
prevent credential leakage into that context (`services/context_pack_builder.py`):

1. **Secret-file exclusion** — files matching `security/secret_paths.py`
   (`.env`, `*.pem`, `*.key`, `id_rsa`, `.aws/`, `.ssh/`, `.docker/config.json`, …)
   are never read into a prompt. Safe templates (`.env.example`) are allowed.
2. **Inline redaction** — content that *is* included is passed through
   `redact_string`, scrubbing API keys, bearer/JWT tokens, and private-key blocks
   before the prompt leaves the machine.

### LLM Provider Boundary

- All Anthropic SDK errors are mapped to a typed `LLMError` hierarchy
  (`exceptions.py`) so failures are actionable, not opaque stack traces.
- Every call is bounded by a configurable timeout (default 120s) with exponential
  backoff on rate-limit / server errors.

### Legacy image-run execution (`ddk run` / `ddk demo`)

- Generated code is copied into a disposable `TempDirSandbox`; unsafe external/absolute
  symlinks are excluded while safe relative in-repo symlinks are preserved.
- Generated artifact paths are canonical repository-relative paths. Absolute paths,
  `..`, Windows drive/UNC paths, and symlink crossings are rejected at both model
  validation and filesystem write boundaries.
- Build commands are validated against an allowlist before execution.
- Subprocess environment variables are allowlisted, secrets are omitted, and `HOME` plus
  the npm cache are redirected into the disposable workspace.
- Execution timeouts are enforced to prevent resource exhaustion.

`TempDirSandbox` is workspace isolation, not an OS/container security boundary. It does
not deny host filesystem reads by an intentionally malicious package script, disable
network access, or impose CPU/memory limits. Run validation only for repositories and
dependency scripts you trust.

### Existing-change execution (`ddk change`)

Default `isolated` verification uses separate app/checker containers on a local Docker daemon,
immutable preinstalled images, no external network, no host port or Docker socket, read-only system
files, dropped capabilities, seccomp and CPU/memory/process/time limits. Chromium runs headless
with its sandbox enabled. Missing isolation or environment evidence blocks verification rather
than falling back to host execution. `trusted-local` requires an explicit user grant and runs
project commands with user permissions; MCP does not expose that grant.

The local daemon and checker image are trusted. Writable source copies have no separate disk quota,
so isolation is not whole-host protection from malicious code. Actual host/framework coverage and
all input constraints are described in the [verified-change guide](docs/VERIFIED-CHANGES.md).

Managed apply requires exact run/change hashes, unchanged originals, local storage and quiescence
confirmation. Recovery handles interrupted owned transactions while preserving external changes.
Legacy `--force`, `--allow-blocked` and whole-repository `ddk rollback` are disabled. A passing
verification is not a security audit of the application.

### Publication boundaries

Internal plans/reviews, launch drafts and raw execution evidence are excluded from Git and source
distributions; runtime schemas and synthetic fixtures remain public. Default change exports omit
sensitive evidence, but review every artifact before sharing. Ignore rules do not erase old commits
or replace secret scanning. If a credential was committed, revoke it and assess history separately.

### Dependency Security

- `pip-audit` runs in CI on every push to detect known CVEs.
- Dependency versions are pinned in `uv.lock` for reproducible builds.
- Only well-maintained, actively-supported dependencies are used.

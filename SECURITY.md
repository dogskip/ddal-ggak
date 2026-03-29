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
   [GitHub Security Advisories](https://github.com/your-org/ddalggak/security/advisories/new).
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

### Sandbox Execution

- Generated code runs in a sandboxed `TempDirSandbox` with policy enforcement.
- Commands are validated against an allowlist before execution.
- Environment variables are filtered — only approved variables are passed to subprocesses.
- Execution timeouts are enforced to prevent resource exhaustion.

### Dependency Security

- `pip-audit` runs in CI on every push to detect known CVEs.
- Dependency versions are pinned in `uv.lock` for reproducible builds.
- Only well-maintained, actively-supported dependencies are used.

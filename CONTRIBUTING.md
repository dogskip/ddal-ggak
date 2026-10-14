# Contributing to ddalggak

Thank you for your interest in contributing to ddalggak!

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Getting Started

```bash
# Clone the repository
git clone https://github.com/dogskip/ddal-ggak.git
cd ddal-ggak

# Install dependencies (dev extras)
uv sync --extra dev

# Verify setup
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest -m "not playwright"
```

`ddk demo` needs Node.js (20.19+ or 22.12+) and a Chrome, Edge or Chromium; `ddk doctor` tells you
what is missing.

## Code Quality Standards

All contributions must pass four quality gates:

1. **Linting**: `uv run ruff check .`
2. **Formatting**: `uv run ruff format --check .`
3. **Type checking**: `uv run pyright` (strict, over `src/`)
4. **Tests**: `uv run pytest -m "not playwright" --tb=short`

The opt-in end-to-end tests run the real loop (npm, Chromium, screenshot comparison):
`DDK_E2E=1 uv run pytest tests/e2e -m playwright`. CI runs them in their own job.

### Code Style

- Follow PEP 8 via `ruff` (configured in `pyproject.toml`)
- Type hints on all public functions
- Docstrings on all public functions and classes
- No `# type: ignore` without a specific error code

### Architecture Rules

ddalggak follows Clean Architecture (D-05):

- **`models/`** — Pydantic data models (no I/O, no side effects)
- **`services/`** — Business logic (depends on models + protocols)
- **`graph/nodes/`** — Thin adapters only (no logic, just plumbing)
- **`adapters/`** — External integrations (implements protocols)

Dependency direction: `nodes → services → models`. Services reach the outside world through
protocols; a few helpers that live in adapter modules (JSON parsing, image flattening, the
`BrowserUnavailableError` type) may be imported, but concrete adapters are constructed only in the
CLI layer (`cli/`, `demo/`, `server.py`).

## Pull Request Process

1. Fork and create a feature branch from `main`
2. Write tests first (TDD preferred)
3. Implement changes
4. Run all quality gates locally
5. Submit PR with a clear description

### Commit Messages

Use conventional commit format:

```
feat: add new validation rule for CSS imports
fix: prevent false-positive release gate on empty state
test: add unit tests for Phase 1-3 graph nodes
docs: update API key configuration guide
```

## Testing

### Test Structure

```
tests/
├── unit/          # Fast, isolated unit tests
│   ├── models/    # Pydantic model tests
│   ├── services/  # Service logic tests
│   ├── adapters/  # Adapter tests with fake Playwright and subprocesses
│   ├── demo/      # The built-in demo
│   └── phase4/    # Error recovery node tests
├── integration/   # Cross-module integration tests
├── contract/      # Interface contract tests
├── e2e/           # Opt-in: real npm, Chromium and screenshots (DDK_E2E=1)
└── fakes/         # Test doubles (fake adapters)
```

### Running Specific Tests

```bash
# All tests
uv run pytest tests/ -q

# Unit tests only
uv run pytest tests/unit/ -q

# Integration tests
uv run pytest tests/integration/ -q

# Skip Playwright tests (requires Chromium)
uv run pytest tests/ -q -m "not playwright"

# With coverage
uv run pytest tests/ --cov=src/ddk --cov-report=term-missing
```

### Pictures in the README

`uv run python scripts/make_readme_assets.py` runs a real `ddk demo` and rebuilds `docs/assets/`
(the terminal recording, the before/after image, the report screenshot and the social preview).
Run it again when the demo output or the report layout changes.

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)

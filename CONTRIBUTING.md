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
uv sync --frozen --extra dev

# Verify setup
uv run ruff check src/ tests/ scripts/ && uv run ruff format --check src/ tests/ scripts/
uv run pyright
uv run pytest -m "not playwright and not docker"
```

`ddk demo` needs Node.js (20.19+ or 22.12+) and a Chrome, Edge or Chromium; `ddk doctor` tells you
what is missing.

## Code Quality Standards

All contributions must pass four quality gates:

1. **Linting**: `uv run ruff check src/ tests/ scripts/`
2. **Formatting**: `uv run ruff format --check src/ tests/ scripts/`
3. **Type checking**: `uv run pyright` (strict, over `src/`)
4. **Tests**: `uv run pytest -m "not playwright and not docker" --tb=short`

The opt-in end-to-end tests run the real loop (npm, Chromium, screenshot comparison):
`DDK_E2E=1 uv run pytest tests/e2e -m playwright`. CI runs them in their own job.

Repair regression coverage includes proposal/cycle/budget/cancellation cases and a real headless
repair-to-apply flow. Provider network tests use the real SDK with a mock transport; ordinary CI does
not send source to a paid provider.

Real isolated execution is a separate opt-in: `DDK_DOCKER_E2E=1`, `DDK_APP_IMAGE` and
`DDK_CHECKER_IMAGE` must identify prebuilt local immutable images, then run
`uv run pytest tests/e2e/test_verified_isolated.py -m docker`. It never pulls images and is not part
of ordinary CI. See the [verified-change guide](docs/VERIFIED-CHANGES.md) for image prerequisites.

### Code Style

- Follow PEP 8 via `ruff` (configured in `pyproject.toml`)
- Type hints on all public functions
- Docstrings on all public functions and classes
- No `# type: ignore` without a specific error code

### Architecture Rules

ddalggak separates responsibilities by layer:

- **`models/`** — Pydantic data models (no I/O, no side effects)
- **`services/`** — Business logic (depends on models + protocols)
- **`graph/nodes/`** — Thin adapters only (no logic, just plumbing)
- **`adapters/`** — External integrations (implements protocols)

Dependency direction: `nodes → services → models`. Services reach the outside world through
protocols; a few helpers that live in adapter modules (JSON parsing, image flattening, the
`BrowserUnavailableError` type) may be imported, but concrete adapters are constructed only in the
CLI layer (`cli/`, `demo/`, `server.py`).

## Pull Request Process

1. Fork and create a contribution branch from `main`; `main` is the sole maintained project branch
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
uv run pytest tests/ -q -m "not playwright and not docker"

# With coverage
uv run pytest tests/ --cov=src/ddk --cov-report=term-missing
```

### Pictures in the README

`uv run python scripts/make_readme_assets.py` runs a real `ddk demo` and rebuilds `docs/assets/`
(the terminal recording, the before/after image, the report screenshot and the social preview).
Run it again when the demo output or the report layout changes.

### Public and local documentation

Update English/Korean README and user guides, security notes and changelog when behavior changes.
Use [ROADMAP.md](ROADMAP.md) and [ROADMAP.ko.md](ROADMAP.ko.md) for planned outcomes and acceptance
criteria; do not describe planned commands as shipped.

Keep public usage docs, runtime schemas under `src/ddk/assets/`, synthetic fixtures under
`tests/fixtures/` and README images in Git. Internal plans/reviews (`.planning/`, `docs/design/`,
`docs/superpowers/`), launch drafts (`docs/launch/`) and raw evidence (`evidence/`) are local-only.
Do not force-add them. Tests and runtime behavior must work without these directories. Ignore rules
do not remove past commits or make shared reports safe.

Before publishing a package, run `uv build` and `uv run python scripts/check_wheel.py dist/*`.
This checks both wheel and source-archive assets and rejects private material. CI also validates
the installed contract without relying on the checkout's internal documents.

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)

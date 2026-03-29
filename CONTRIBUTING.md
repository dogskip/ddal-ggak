# Contributing to ddalggak

Thank you for your interest in contributing to ddalggak!

## Development Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

### Getting Started

```bash
# Clone the repository
git clone https://github.com/your-org/ddalggak.git
cd ddalggak

# Install dependencies (dev extras)
uv sync --extra dev --extra visual

# Verify setup
uv run ruff check src/ tests/
uv run pyright src/
uv run pytest tests/ -q
```

## Code Quality Standards

All contributions must pass three quality gates:

1. **Linting**: `uv run ruff check src/ tests/`
2. **Type checking**: `uv run pyright src/`
3. **Tests**: `uv run pytest tests/ -q --tb=short`

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

Dependency direction: `nodes → services → models`. Never import adapters from services.

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
│   └── phase4/    # Error recovery node tests
├── integration/   # Cross-module integration tests
├── contract/      # Interface contract tests
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

## Reporting Issues

- Use GitHub Issues for bugs and feature requests
- For security vulnerabilities, see [SECURITY.md](SECURITY.md)

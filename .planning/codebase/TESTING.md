# Testing Patterns

**Analysis Date:** 2025-01-19

## Test Framework

**Runner:**
- pytest 8.0.0+
- Config: `pyproject.toml` (`[tool.pytest.ini_options]`)
- asyncio_mode = "auto" — async tests don't need `@pytest.mark.asyncio`
- pythonpath = ["src"] — allows `from ddk...` imports in tests

**Assertion Library:**
- pytest built-in assertions via `assert` statements
- No specialized assertion library; plain `assert` throughout

**Run Commands:**
```bash
pytest tests/                           # Run all tests
pytest tests/unit/                      # Run unit tests only
pytest tests/integration/               # Run integration tests
pytest -m "not integration"             # Run only unit tests
pytest -m "not playwright"              # Skip Playwright tests
pytest --cov=src/ddk --cov-report=term # Coverage report
pytest -xvs tests/unit/test_file.py     # Verbose with early exit on failure
```

## Test File Organization

**Location:**
- Co-located with source: mirrored `tests/` structure matches `src/ddk/`
- Example: `src/ddk/services/code_generator.py` → `tests/unit/services/test_code_generator.py`
- Test doubles in `tests/fakes/` directory (all fake adapters centralized)
- Shared fixtures in `tests/conftest.py` (root level)

**Naming:**
- Test files: `test_*.py`
- Test classes: `Test[FeatureName]` (e.g., `TestCodeGenerator`, `TestFakeLLMAdapter`)
- Test methods: `test_[specific_behavior]` (e.g., `test_returns_canned_response`, `test_records_call_log`)

**Structure:**
```
tests/
├── conftest.py                 # Shared fixtures
├── fakes/                      # Test doubles (8 fake adapters)
│   ├── __init__.py
│   ├── fake_llm_adapter.py
│   ├── fake_subprocess.py
│   ├── fake_filesystem.py
│   ├── fake_playwright_adapter.py
│   ├── fake_sandbox.py
│   ├── fake_build_runner.py
│   ├── fake_rollback.py
│   ├── fake_cost_tracker.py
│   ├── fake_fallback_chain.py
│   ├── fake_ssim_adapter.py
│   └── setup.py               # Setup helpers for fakes
├── integration/               # E2E/integration tests (7 test files)
│   ├── test_di_smoke.py
│   ├── test_generation_pipeline.py
│   ├── test_ingestion_pipeline.py
│   └── ...
├── unit/                      # Unit tests (47 test files, 369 test methods)
│   ├── conftest.py           # Unit-specific fixtures (if any)
│   ├── models/               # Model validation tests
│   │   └── test_*.py
│   ├── services/             # Service logic tests
│   │   └── test_*.py
│   ├── phase4/               # Phase-specific tests
│   │   └── test_*.py
│   ├── test_fakes.py         # Behavior tests for all 8 test doubles
│   ├── test_logging.py       # Security redaction tests
│   ├── test_node_wrapper.py  # LangGraph wrapper tests
│   └── ...
└── fixtures/                 # Fixture data (test repos, example configs)
    └── repos/
        └── react-vite-ts/
```

## Test Structure

**Suite Organization:**
```python
class TestCodeGenerator:
    """Group related tests in classes by feature."""
    
    def test_specific_behavior(self) -> None:
        """Sync test."""
        result = some_function()
        assert result == expected
    
    async def test_async_behavior(self) -> None:
        """Async test — no @pytest.mark.asyncio needed."""
        result = await async_function()
        assert result == expected
    
    def test_another_case(self) -> None:
        """Multiple assertions allowed."""
        obj = MyClass()
        assert obj.field == value1
        assert obj.method() == value2
```

**Patterns:**
- Setup: Direct initialization inline or via fixtures
- Teardown: Context managers used when needed; pytest fixtures with yield
- Assertion: `assert` statements with optional error messages: `assert result == expected, "Expected X but got Y"`

## Mocking

**Framework:** `unittest.mock.MagicMock` (standard library)

**Patterns:**
```python
from unittest.mock import MagicMock

def test_with_mock() -> None:
    container = MagicMock()
    container.some_service.return_value = "mocked"
    
    # Verify mock was called
    container.some_service.assert_called()
    assert container.some_service.call_count == 1
```

**What to Mock:**
- External service adapters: LLM calls, file I/O, subprocess runners
- Mocked via fake adapters preferentially (more controlled): `FakeLLMAdapter`, `FakePlaywrightAdapter`
- MagicMock used for container/DI mocking in node tests

**What NOT to Mock:**
- Models and Pydantic validation (test real behavior)
- Protocol conformance (assert `isinstance(fake, Protocol)`)
- Pure functions and deterministic helpers (test directly)
- Database/filesystem (use in-memory fakes: `InMemoryFilesystem`)

## Fixtures and Factories

**Test Data:**
```python
# From tests/fakes/fake_llm_adapter.py
class FakeLLMAdapter:
    def __init__(self, responses: dict[str, str | dict[str, Any]] | None = None):
        self.responses: dict[str, str | dict[str, Any]] = responses or {}
        self.call_log: list[dict[str, Any]] = []

# Usage in test:
@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    return FakeLLMAdapter(responses={"default": "fake response"})

async def test_llm_call(fake_llm: FakeLLMAdapter) -> None:
    result = await fake_llm.complete([...])
    assert result.content == "fake response"
    assert len(fake_llm.call_log) == 1
```

**Location:**
- Fixtures in `tests/conftest.py` (root) for shared fixtures
- Fake adapters in `tests/fakes/*.py` (8 dedicated test doubles)
- Fixture setup code in `tests/fakes/setup.py`
- Test-specific fixtures inline in test files or `conftest.py` nearest to tests

**8 Core Test Doubles:**
1. `FakeLLMAdapter` — Returns canned responses keyed by system prompt first word; records call log
2. `InMemoryFilesystem` — Dict-backed file I/O; satisfies `FilesystemPort` protocol
3. `FakeSubprocessRunner` — Returns pre-configured BuildResult; records all commands run
4. `FakePlaywrightAdapter` — Returns fake screenshot paths; implements PlaywrightAdapter protocol
5. `TempDirSandbox` — Creates temporary directories; cleans up after tests
6. `FakeBuildRunner` — Simulates build command execution
7. `FakeRollbackController` — Simulates rollback behavior
8. `FakeFallbackChain` — Simulates fallback/retry patterns

## Coverage

**Requirements:** No hard target visible; 441 tests passing

**View Coverage:**
```bash
pytest --cov=src/ddk --cov-report=term
pytest --cov=src/ddk --cov-report=html  # Generates htmlcov/index.html
```

## Test Types

**Unit Tests (369 test methods):**
- Scope: Individual functions, classes, and adapters
- Location: `tests/unit/`
- Examples:
  - `tests/unit/models/test_base_models.py` — Pydantic model validation
  - `tests/unit/phase4/test_auto_fix_planner.py` — Service logic (8 deterministic rules + LLM dispatch)
  - `tests/unit/services/test_code_generator.py` — CodeGenerator with fake LLM

**Integration Tests (7 files):**
- Scope: Full workflows, pipeline execution, DI container verification
- Location: `tests/integration/`
- Markers: `@pytest.mark.integration` — requires ANTHROPIC_API_KEY
- Examples:
  - `test_generation_pipeline.py` — Full generation pipeline with real/fake adapters
  - `test_ingestion_pipeline.py` — Intake → normalization → validation flow
  - `test_di_smoke.py` — ServiceContainer construction smoke test

**Playwright Tests (2+ files):**
- Scope: Visual regression, browser automation
- Markers: `@pytest.mark.playwright` — requires browser binaries
- Example: `test_phase4_playwright.py` — Screenshot diff validation

## Common Patterns

**Async Testing:**
```python
# asyncio_mode = "auto" in pyproject.toml — just use async def
async def test_async_operation(self) -> None:
    result = await async_function()
    assert result is not None
```

**Error Testing:**
```python
def test_raises_on_missing_key(self) -> None:
    fake = FakeLLMAdapter(responses={})
    with pytest.raises(ValueError, match="no fixture for key"):
        await fake.complete([...])

def test_validation_error_on_extra_fields(self) -> None:
    with pytest.raises(ValidationError):
        MyModel(name="test", unknown_field="bad")
```

**Parametrized Tests:**
```python
@pytest.mark.parametrize(
    "input_value,expected",
    [
        ("test1", "result1"),
        ("test2", "result2"),
    ],
)
def test_multiple_cases(input_value: str, expected: str) -> None:
    assert function(input_value) == expected
```

**Fixtures with Monkeypatch:**
```python
@pytest.fixture
def env_var_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_KEY", "test-key")
```

## Fixture Patterns from conftest.py

```python
@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for workspace tests."""
    (tmp_path / "package.json").write_text('{"name": "test-project"}')
    return tmp_path

@pytest.fixture
def fake_llm() -> FakeLLMAdapter:
    """Pre-configured FakeLLMAdapter with a default response."""
    return FakeLLMAdapter(responses={"default": "fake response"})

@pytest.fixture
def in_memory_fs() -> InMemoryFilesystem:
    """Empty InMemoryFilesystem instance."""
    return InMemoryFilesystem()

@pytest.fixture(scope="session")
def anthropic_api_key() -> str:
    """Return API key or skip test if not set."""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set — skipping integration test")
    return key
```

## Test Double Lifecycle Example

```python
# From tests/unit/test_fakes.py

class TestFakeLLMAdapter:
    async def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeLLMAdapter(), LLMAdapter)

    async def test_returns_canned_response(self) -> None:
        fake = FakeLLMAdapter(responses={"hello": "world"})
        msgs = [Message(role="system", content="hello there")]
        result = await fake.complete(msgs, LLMCallConfig())
        assert result.content == "world"

    async def test_records_call_log(self) -> None:
        fake = FakeLLMAdapter(responses={"test": "ok"})
        msgs = [Message(role="system", content="test prompt")]
        await fake.complete(msgs, LLMCallConfig())
        assert len(fake.call_log) == 1
        assert fake.call_log[0]["key"] == "test"

    async def test_raises_on_missing_key(self) -> None:
        fake = FakeLLMAdapter(responses={})
        msgs = [Message(role="system", content="unknown prompt")]
        with pytest.raises(ValueError, match="no fixture for key"):
            await fake.complete(msgs, LLMCallConfig())

    async def test_dict_response_becomes_json(self) -> None:
        fake = FakeLLMAdapter(responses={"data": {"key": "value"}})
        msgs = [Message(role="system", content="data payload")]
        result = await fake.complete(msgs, LLMCallConfig())
        assert '"key"' in result.content
```

## Configuration & Warnings

**pytest.ini_options:**
- asyncio_mode = "auto" (pytest-asyncio)
- testpaths = ["tests"]
- pythonpath = ["src"]
- markers defined for `integration` and `playwright`
- filterwarnings suppress "Core Pydantic V1" warnings

**Skipping Tests:**
```bash
pytest -m "not integration"       # Skip integration tests
pytest -m "not playwright"        # Skip Playwright tests
pytest --ignore=tests/integration # Ignore entire directory
```

## Test Quality Notes

- 441 tests passing with structured test doubles
- Protocol conformance verified: `assert isinstance(fake, LLMAdapter)`
- Call logging on all fakes for verification and debugging
- Deterministic behavior (no flakiness) via canned responses and in-memory storage
- TDD approach observed: models → protocol → fake → DI → service → CLI

---

*Testing analysis: 2025-01-19*

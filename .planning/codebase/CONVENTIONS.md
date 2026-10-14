# Coding Conventions

**Analysis Date:** 2025-01-19

## Naming Patterns

**Files:**
- Modules use `snake_case`: `auto_fix_planner.py`, `code_generator.py`, `local_git.py`
- Adapter files use service names: `llm/claude.py`, `sandbox/tempdir.py`, `screenshot_diff_local.py`
- Test files: `test_*.py` in corresponding module structure
- Internal helper files prefixed with underscore: `_wrapper.py`, `_base.py`

**Functions:**
- Module-level functions use `snake_case`: `r01_remove_unused_import()`, `_extract_context()`, `_split_messages()`
- Private/helper functions prefixed with single underscore: `_extract_context()`, `_extract_runtime_context()`, `_extract_key()`
- Async functions use `async def`: `async def complete()`, `async def generate_all()`, `async def run()`
- No naming distinction between sync and async beyond keyword presence

**Variables:**
- Local variables use `snake_case`: `key`, `content`, `result`, `messages`
- Constants in uppercase: internal module constants
- Instance variables prefixed with underscore in classes: `self._llm`, `self._config`, `self.responses`
- Type hint usage of `|` for unions (PEP 604): `str | int | None`, `dict[str, Any] | None`

**Types:**
- Pydantic models inherit from `DDKBaseModel` (frozen=False, validate_assignment=True): `class BoundingBox(DDKBaseModel)`, `class IntentGraph(DDKBaseModel)`
- Protocol classes use `@runtime_checkable` and `Protocol`: `class LLMAdapter(Protocol)`, `class BuildRunner(Protocol)`
- Enum values use lowercase with underscores: `ErrorCategory.LLM`, `ErrorSeverity.CRITICAL`, `region_type: Literal["header", "nav", ...]`
- Dataclasses for configuration/transfer objects: `@dataclass class Message`, `@dataclass class LLMCallConfig`, `@dataclass class BuildResult`

## Code Style

**Formatting:**
- Tool: `ruff` (linter + formatter)
- Line length: 100 characters (configured in `tool.ruff` section)
- Target version: Python 3.12

**Linting:**
- Tool: `ruff`
- Selected rules: `["E", "F", "I", "N", "UP", "B", "C4", "SIM"]`
  - E: pycodestyle errors
  - F: Pyflakes
  - I: isort (import sorting)
  - N: pep8-naming
  - UP: pyupgrade
  - B: flake8-bugbear
  - C4: flake8-comprehensions
  - SIM: flake8-simplify
- Type checking: `pyright` in strict mode (`typeCheckingMode = "strict"`)

**Suppressions:**
- `# noqa: [CODE]` for specific rule suppressions (e.g., `# noqa: BLE001` for bare except, `# noqa: PLC0415` for late imports)
- `# type: ignore[...]` for pyright overrides (e.g., `# type: ignore[arg-type]`, `# type: ignore[var-annotated]`)
- `# pyright: ignore[...]` for pyright-specific suppressions (e.g., `# pyright: ignore[reportPrivateImportUsage]`)
- Used sparingly with justification in comments or code context

## Import Organization

**Order:**
1. `from __future__ import annotations` (always first, enables PEP 563 postponed evaluation)
2. Standard library imports (`import asyncio`, `import json`, `from pathlib import Path`)
3. Third-party imports (`import typer`, `import pytest`, `from pydantic import BaseModel`)
4. Relative imports from this package (`.models.intent`, `..adapters.llm.base`)
5. Type-only imports guarded with `TYPE_CHECKING` if needed

**Example from `services/auto_fix_planner.py`:**
```python
from __future__ import annotations

import json
import re
import time
from typing import Any

from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.models.fix import FixAttempt
from ddk.models.validation import FailureRecord
```

**Path Aliases:**
- No path aliases configured
- All imports use absolute paths from `ddk` package root
- Example: `from ddk.adapters.llm.base import LLMAdapter` (not relative)

## Error Handling

**Patterns:**
- Specific exception catching with type annotations
- Wrapped exceptions in node infrastructure: try/except blocks catch specific + generic errors
- Example from `src/ddk/graph/nodes/_wrapper.py`:
  ```python
  try:
      return await node_fn(state, **kwargs)
  except (OSError, PermissionError, TimeoutError) as exc:
      return {
          "terminal_state": "manual-review-required",
          "error_message": f"OS/timeout error in node: {exc}",
      }
  except Exception as exc:  # noqa: BLE001
      return {
          "terminal_state": "manual-review-required",
          "error_message": f"Unexpected error: {type(exc).__name__}: {exc}",
      }
  ```
- Error hierarchy in `src/ddk/models/errors.py`: `DDKError` base model with `ErrorCategory`, `ErrorSeverity` enums, `ErrorChain` for collections
- `ValueError` raised for missing/invalid conditions: `raise ValueError(f"FakeLLMAdapter: no fixture for key '{key}'")`
- `ValidationError` from Pydantic for model validation: models raise automatically

## Logging

**Framework:** No centralized logging in core services observed; structlog imported but not extensively used in sampled files

**Patterns:**
- Security-aware logging with `redact_string()` and `redact_dict()` utilities in `src/ddk/security/redact.py`
- Rich progress/output via CLI: `Console`, `Panel`, `Progress` from `rich` library
- No explicit logging statements in service methods (design is functional/return-based)

## Comments

**When to Comment:**
- Docstrings on all public functions and classes (triple-quoted strings with description)
- Section headers as ASCII comments for readability: `# ───────────────────────────────`, `# Rule functions`, `# Test setup`
- Inline comments for complex regex or logic: Example in `auto_fix_planner.py` shows rule implementations with clear names
- No redundant comments; code is self-documenting via naming

**JSDoc/TSDoc:**
- Used for key functions and classes with `"""Docstring here."""` format
- Includes purpose, Args, Returns, and Raises sections when applicable
- Example from `src/ddk/graph/nodes/_wrapper.py`:
  ```python
  def node_wrapper(
      node_fn: Callable[..., Any],
  ) -> Callable[..., Any]:
      """Return an async error-boundary wrapper around a LangGraph node function.

      The returned coroutine:
      - Extracts the ServiceContainer from LangGraph's RunnableConfig
      - Catches OS/permission/timeout errors and returns a safe error state

      Args:
          node_fn: The real async node function to wrap.

      Returns:
          An async callable with the same signature as ``node_fn``.
      """
  ```

## Function Design

**Size:**
- Service methods: 20–80 lines typical (some generators/planners up to 150 lines)
- Keep helper functions small and focused
- Private helpers prefixed with `_` for single-file scope

**Parameters:**
- Type hints required: all parameters annotated with types
- Use dataclass/Pydantic models for grouping related parameters
- Default parameters used (e.g., `timeout: int = 300`)
- Context injection pattern: async functions accept optional `context` parameter via kwargs for DI

**Return Values:**
- Explicit return type hints: `-> str`, `-> dict[str, Any]`, `-> LLMResponse`, `-> list[str] | None`
- Single return statement preferred; multiple allowed for guards
- Functions typically return data structures (not None) or raise exceptions
- Async functions return coroutine-wrapped results

## Module Design

**Exports:**
- Public API explicitly defined via import statements (no `__all__` lists visible)
- Models, services, adapters clearly separate
- Example structure: `from ddk.services.auto_fix_planner import AutoFixPlanner, r01_remove_unused_import`

**Barrel Files:**
- `__init__.py` in adapters/llm imports key exports:
  ```python
  from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
  from ddk.adapters.llm.claude import ClaudeAdapter
  ```
- Test fixtures in `tests/fakes/__init__.py` aggregate test doubles
- No star imports (`from X import *`) observed in source code

## Type Annotations

**Strictness:**
- Pyright strict mode enabled (`typeCheckingMode = "strict"`)
- All function parameters and returns annotated
- Generic types used: `dict[str, Any]`, `list[str]`, `tuple[str, str] | None`
- Optional types via `| None` union syntax (PEP 604)
- Protocol classes for adapter abstraction

**Exception Suppression:**
- Bare except `Exception` caught only in wrapping code (node_wrapper): `except Exception as exc:  # noqa: BLE001`
- Specific exception types caught when possible

## Example: Service Class Structure

From `src/ddk/services/code_generator.py`:
```python
class CodeGenerator:
    """Calls the LLM once per planned node and assembles a GeneratedArtifactSet."""

    def __init__(self, llm: LLMAdapter, model: str = DEFAULT_PRIMARY_MODEL) -> None:
        self._llm = llm
        self._config = LLMCallConfig(
            model=model,
            temperature=0.0,
            max_tokens=4096,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_all(
        self,
        plan: GenerationPlan,
        repo_profile: RepoProfile,
    ) -> GeneratedArtifactSet:
        """Public async method with type hints and section comment."""
        ...

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _generate_node(self, ...) -> dict[str, Any]:
        """Private helper with underscore prefix."""
        ...
```

---

*Convention analysis: 2025-01-19*

---
phase: 04-validation-self-healing
plan: "01"
subsystem: infrastructure
tags: [wave-0, dependencies, state, fakes, playwright]
dependency_graph:
  requires: []
  provides: [phase4-fakes, failure-hash-history, failed-request-entry, build-runner-fake, ssim-fake]
  affects: [all-phase4-waves]
tech_stack:
  added: [scikit-image>=0.21.0, Pillow>=10.0.0, playwright>=1.44.0, pytest-playwright>=0.5.0]
  patterns: [Protocol fake, TypedDict additive extension, dataclass entry type]
key_files:
  created:
    - tests/fakes/fake_build_runner.py
    - tests/fakes/fake_ssim_adapter.py
    - tests/unit/phase4/__init__.py  # requires manual mkdir (see below)
  modified:
    - pyproject.toml
    - src/ddk/graph/state.py
    - src/ddk/adapters/playwright_browser.py
    - tests/fakes/fake_playwright_adapter.py
    - tests/fakes/__init__.py
decisions:
  - "failure_hash_history placed after pre_run_checkpoint_ref in GraphState for logical grouping (oscillation detection is a control-flow concern)"
  - "FailedRequestEntry uses str for failure_text (not str | None) to avoid None guards in callers — Playwright guarantees non-null when request.failure is called on a failed request"
  - "FakeSSIMAdapter.generate_diff_image returns output path unchanged — sufficient for unit tests that only check call recording"
metrics:
  duration: "~15min (file edits only; shell unavailable)"
  completed: "2025-06-06"
  tasks_completed: 3
  files_changed: 7
---

# Phase 4 Plan 01: Wave 0 — Foundation & Plumbing Summary

**One-liner:** Additive pyproject.toml deps (scikit-image, Pillow, playwright), `failure_hash_history: list[int]` in GraphState, `FailedRequestEntry` + `get_failed_requests()` in PlaywrightAdapter protocol, and FakeBuildRunner/FakeSSIMAdapter test doubles.

---

## What Was Done

### Packages Added to pyproject.toml

| Package | Version | Section |
|---------|---------|---------|
| `scikit-image` | `>=0.21.0` | `[project.dependencies]` |
| `Pillow` | `>=10.0.0` | `[project.dependencies]` |
| `playwright` | `>=1.44.0` | `[project.dependencies]` |
| `pytest-playwright` | `>=0.5.0` | `[project.optional-dependencies].dev` |

Marker registered in `[tool.pytest.ini_options].markers`:
```
"playwright: requires Playwright + browser binaries (skip in CI with -m 'not playwright')"
```

### State Fields Added (additive)

**`src/ddk/graph/state.py`**

```python
# In GraphState TypedDict (after pre_run_checkpoint_ref):
failure_hash_history: list[int]  # oscillation detection — appended each validate cycle

# In initial_state() factory:
failure_hash_history=[],
```

No existing fields were renamed, deleted, or reordered.

### Protocol Extensions Added (additive)

**`src/ddk/adapters/playwright_browser.py`**

New dataclass after `ConsoleEntry`:
```python
@dataclass
class FailedRequestEntry:
    url: str
    failure_text: str
    correlation_id: str | None = None
```

New method in `PlaywrightAdapter` protocol (after `get_console_errors`):
```python
async def get_failed_requests(
    self, url: str, wait_ms: int = 5000,
    correlation_id: str | None = None,
) -> list[FailedRequestEntry]: ...
```

### Fakes Created

| File | Class | Purpose |
|------|-------|---------|
| `tests/fakes/fake_build_runner.py` | `FakeBuildRunner` | Configurable `CommandResult` (returncode, stdout, stderr) with `run_log` |
| `tests/fakes/fake_ssim_adapter.py` | `FakeSSIMAdapter` | Configurable `SSIMResult` (ssim_score, diff_path) with `compute_log` |
| `tests/fakes/fake_playwright_adapter.py` | `FakePlaywrightAdapter` | Extended with `failed_requests: list[FailedRequestEntry]` + `get_failed_requests()` |

**`tests/fakes/__init__.py`** updated to export `FakeBuildRunner` and `FakeSSIMAdapter`.

**`tests/unit/phase4/__init__.py`** — package marker file (requires manual creation, see below).

---

## Deviations from Plan

### Environment Blocker: Bash Unavailable

**Found during:** All tasks

**Issue:** The bash execution tool returns `posix_spawn failed: No such file or directory` for all commands in this session. This affects: `uv sync`, `uv run playwright install chromium`, `pytest`, `pyright`, `ruff`, `git commit`, and `mkdir`.

**Impact:** 
1. `tests/unit/phase4/` directory could not be created (no bash = no mkdir)
2. `uv sync` not run — new packages not yet installed in venv
3. `playwright install chromium` not run — browser binary not installed
4. Verification commands not run
5. Git commits not made

**Fix required (manual):** Run the commands in the section below.

---

## ⚠️ Required Manual Steps

Run these commands from the project root:

```bash
cd /Users/bjchoi/SynologyDrive/projects/test/ddalggak

# 1. Create phase4 test package directory
mkdir -p tests/unit/phase4
echo '"""Phase 4 unit tests — Validation & Self-Healing."""' > tests/unit/phase4/__init__.py

# 2. Install new dependencies
uv sync

# 3. Install Playwright browser binary (~150MB, one-time)
uv run playwright install chromium

# 4. Verify imports
uv run python -c "import skimage; import PIL; import playwright; print('deps OK')"

# 5. Verify fakes + state
uv run python -c "
from tests.fakes.fake_build_runner import FakeBuildRunner
from tests.fakes.fake_ssim_adapter import FakeSSIMAdapter
from ddk.adapters.playwright_browser import FailedRequestEntry, PlaywrightAdapter
from ddk.graph.state import GraphState, initial_state
from ddk.models.input import CaseInput
import uuid
ci = CaseInput(case_id=str(uuid.uuid4()), prompt='test', image_refs=[])
s = initial_state(ci)
assert 'failure_hash_history' in s
assert s['failure_hash_history'] == []
print('ALL CHECKS PASSED')
"

# 6. Full regression test suite
uv run pytest tests/ -x -q -m 'not playwright' 2>&1 | tail -15

# 7. Pyright strict
uv run pyright src/ddk/graph/state.py src/ddk/adapters/playwright_browser.py

# 8. Ruff
uv run ruff check src/ tests/fakes/

# 9. Commit all changes
git add pyproject.toml uv.lock
git add src/ddk/graph/state.py
git add src/ddk/adapters/playwright_browser.py
git add tests/fakes/fake_playwright_adapter.py
git add tests/fakes/fake_build_runner.py
git add tests/fakes/fake_ssim_adapter.py
git add tests/fakes/__init__.py
git add tests/unit/phase4/__init__.py
git commit -m "feat(04-01): Wave 0 — add deps, failure_hash_history, FailedRequestEntry, FakeBuildRunner, FakeSSIMAdapter

- pyproject.toml: add scikit-image>=0.21.0, Pillow>=10.0.0, playwright>=1.44.0
- pyproject.toml: add pytest-playwright>=0.5.0 (dev), playwright marker
- state.py: additive failure_hash_history: list[int] in GraphState + initial_state()
- playwright_browser.py: additive FailedRequestEntry dataclass + get_failed_requests() protocol method
- fake_playwright_adapter.py: additive failed_requests list + get_failed_requests() impl
- tests/fakes/fake_build_runner.py: new FakeBuildRunner test double
- tests/fakes/fake_ssim_adapter.py: new FakeSSIMAdapter test double
- tests/unit/phase4/__init__.py: new package marker
"
```

---

## File State Verification

All files are correctly edited (verified via view tool):

| File | Status | Key Content |
|------|--------|-------------|
| `pyproject.toml` | ✅ Edited | scikit-image, Pillow, playwright, pytest-playwright, playwright marker |
| `src/ddk/graph/state.py` | ✅ Edited | `failure_hash_history: list[int]` in TypedDict + `failure_hash_history=[]` in factory |
| `src/ddk/adapters/playwright_browser.py` | ✅ Edited | `FailedRequestEntry` dataclass + `get_failed_requests()` in protocol |
| `tests/fakes/fake_playwright_adapter.py` | ✅ Edited | `failed_requests: list[FailedRequestEntry]`, `get_failed_requests()` |
| `tests/fakes/fake_build_runner.py` | ✅ Created | `FakeBuildRunner` with configurable returncode/stdout/stderr + run_log |
| `tests/fakes/fake_ssim_adapter.py` | ✅ Created | `FakeSSIMAdapter` with configurable ssim_score + compute_log |
| `tests/fakes/__init__.py` | ✅ Edited | Exports `FakeBuildRunner`, `FakeSSIMAdapter` |
| `tests/unit/phase4/__init__.py` | ❌ Pending | Needs `mkdir -p tests/unit/phase4` first |

## Self-Check: PARTIAL

File edits verified via view tool. Shell execution (uv sync, tests, git commits) blocked by bash unavailability. Manual steps required above.

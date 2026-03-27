---
phase: 01-foundation-core-infrastructure
plan: 04
subsystem: infra
tags: [protocol, adapter, sandbox, security, typing, runtime-checkable]

# Dependency graph
requires:
  - phase: 01-01
    provides: "DDKBaseModel, Pydantic v2 base, package structure with adapters/__init__.py"
provides:
  - "7 @runtime_checkable Protocol interfaces (LLMAdapter, FilesystemPort, GitAdapter, SandboxAdapter, BuildRunner, PlaywrightAdapter, ScreenshotDiffAdapter)"
  - "FilesystemAdapter real implementation"
  - "Sandbox execution policy (ENV_WHITELIST, FORBIDDEN_READ_PATHS, ALLOWED_COMMANDS)"
  - "Supporting dataclasses (Message, LLMCallConfig, LLMResponse, CommandResult, BuildResult, ConsoleEntry, SSIMResult)"
affects: [01-05, 02-services, 03-nodes, 04-runtime]

# Tech tracking
tech-stack:
  added: []
  patterns: ["@runtime_checkable Protocol for adapter boundaries", "dataclass for protocol DTOs", "frozenset for immutable security policy constants"]

key-files:
  created:
    - src/ddk/adapters/llm/base.py
    - src/ddk/adapters/filesystem.py
    - src/ddk/adapters/git.py
    - src/ddk/adapters/sandbox/base.py
    - src/ddk/adapters/sandbox/policy.py
    - src/ddk/adapters/build_runner.py
    - src/ddk/adapters/playwright_browser.py
    - src/ddk/adapters/screenshot_diff.py
    - tests/unit/test_protocols.py
    - tests/unit/test_sandbox_policy.py
  modified: []

key-decisions:
  - "Used dataclass (not Pydantic) for Protocol supporting types — lightweight DTOs that don't need validation"
  - "ENV_WHITELIST as frozenset for immutable security — prevents runtime modification"

patterns-established:
  - "Protocol-first adapter pattern: define @runtime_checkable Protocol, then implement separately"
  - "Security policy as module-level constants: frozenset/list for allowlists/blocklists"
  - "Helper functions (is_command_allowed, is_path_forbidden, is_env_allowed) for policy checks"

requirements-completed: [INFRA-03, VALID-06]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 01 Plan 04: Adapter Protocols & Sandbox Policy Summary

**7 @runtime_checkable Protocol interfaces for all adapter boundaries plus sandbox execution policy with ENV_WHITELIST, FORBIDDEN_READ_PATHS, ALLOWED_COMMANDS**

## Performance

- **Duration:** 2 min 29 sec
- **Started:** 2026-03-27T02:22:05Z
- **Completed:** 2026-03-27T02:24:34Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Defined all 7 adapter Protocol interfaces with @runtime_checkable for conformance testing
- Implemented FilesystemAdapter as real implementation satisfying FilesystemPort Protocol
- Created sandbox execution policy (VALID-06) with ENV_WHITELIST, FORBIDDEN_READ_PATHS, ALLOWED_COMMANDS
- 33 tests passing covering Protocol conformance and sandbox policy

## Task Commits

Each task was committed atomically:

1. **Task 1: Define all 7 adapter Protocol interfaces with supporting types** - `70735f5` (feat)
2. **Task 2 RED: Add failing tests for sandbox policy and protocol conformance** - `c59b319` (test)
3. **Task 2 GREEN: Implement sandbox policy and pass protocol conformance tests** - `61f2d80` (feat)

_Task 2 was TDD — RED then GREEN commits._

## Files Created/Modified

- `src/ddk/adapters/llm/base.py` — LLMAdapter Protocol, Message, LLMCallConfig, LLMResponse dataclasses
- `src/ddk/adapters/filesystem.py` — FilesystemPort Protocol + FilesystemAdapter real implementation
- `src/ddk/adapters/git.py` — GitAdapter Protocol (hybrid read/write per D-04)
- `src/ddk/adapters/sandbox/base.py` — SandboxAdapter Protocol + CommandResult dataclass
- `src/ddk/adapters/sandbox/policy.py` — ENV_WHITELIST, FORBIDDEN_READ_PATHS, ALLOWED_COMMANDS + helper functions
- `src/ddk/adapters/build_runner.py` — BuildRunner Protocol + BuildResult dataclass
- `src/ddk/adapters/playwright_browser.py` — PlaywrightAdapter Protocol + ConsoleEntry dataclass
- `src/ddk/adapters/screenshot_diff.py` — ScreenshotDiffAdapter Protocol + SSIMResult dataclass
- `tests/unit/test_protocols.py` — Protocol conformance tests for all 7 adapters + FilesystemAdapter
- `tests/unit/test_sandbox_policy.py` — Sandbox policy tests (ENV_WHITELIST, FORBIDDEN_READ_PATHS, ALLOWED_COMMANDS, helper functions)

## Decisions Made

- Used dataclass (not Pydantic) for Protocol supporting types — these are lightweight DTOs that don't need validation, keeping adapter boundary lean
- ENV_WHITELIST as frozenset for immutable security — prevents runtime modification of security-critical config

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused pytest import in test_sandbox_policy.py**
- **Found during:** Task 2 GREEN phase
- **Issue:** Ruff F401 flagged unused `import pytest` in test_sandbox_policy.py
- **Fix:** Removed the unused import
- **Files modified:** tests/unit/test_sandbox_policy.py
- **Verification:** `ruff check` passes clean
- **Committed in:** 61f2d80 (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 bug — unused import)
**Impact on plan:** Trivial cleanup. No scope creep.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Known Stubs

None - all protocols are intentionally abstract (Protocol interfaces), not stubs. Real implementations will come in later phases.

## Next Phase Readiness

- All 7 adapter Protocol interfaces are defined and ready for concrete implementations
- Sandbox policy is defined and can be used by SandboxAdapter implementations
- FilesystemAdapter provides real implementation for immediate use in tests
- Protocol conformance test pattern established for verifying future adapter implementations

## Self-Check: PASSED

- All 11 files exist on disk
- All 3 task commits verified (70735f5, c59b319, 61f2d80)
- 33 tests passing
- Ruff checks clean

---
*Phase: 01-foundation-core-infrastructure*
*Completed: 2026-03-27*

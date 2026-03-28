---
phase: 1
slug: foundation-core-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2025-07-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest ≥8.0.0 + pytest-asyncio ≥0.23.0 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (create in Wave 0) |
| **Quick run command** | `uv run pytest tests/unit/ -x --tb=short -q` |
| **Full suite command** | `uv run pytest --cov=ddk --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x --tb=short -q`
- **After every plan wave:** Run `uv run pytest --cov=ddk --cov-report=term-missing`
- **Before `/gsd-verify-work`:** Full suite must be green + Ruff lint + Pyright type check
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | INFRA-01 | smoke | `uv run python -c "import ddk"` | ❌ W0 | ⬜ pending |
| 01-02-01 | 02 | 1 | INFRA-02 | unit | `uv run pytest tests/unit/models/ -x` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | INFRA-03 | unit | `uv run pytest tests/unit/test_protocols.py -x` | ❌ W0 | ⬜ pending |
| 01-04-01 | 04 | 2 | INFRA-05 | unit | `uv run pytest tests/unit/test_fakes.py -x` | ❌ W0 | ⬜ pending |
| 01-05-01 | 05 | 3 | INFRA-04 | integration | `uv run pytest tests/integration/test_di_smoke.py -x` | ❌ W0 | ⬜ pending |
| 01-06-01 | 06 | 3 | INFRA-06 | unit | `uv run pytest tests/unit/test_logging.py -x` | ❌ W0 | ⬜ pending |
| 01-07-01 | 07 | 4 | INGEST-01 | integration | `uv run pytest tests/integration/test_init_workspace.py -x` | ❌ W0 | ⬜ pending |
| 01-08-01 | 08 | 4 | VALID-06 | unit | `uv run pytest tests/unit/test_sandbox_policy.py -x` | ❌ W0 | ⬜ pending |
| 01-09-01 | 09 | 4 | CERT-04 | contract | `uv run pytest tests/contract/test_llm_call_record_contract.py -x` | ❌ W0 | ⬜ pending |
| 01-10-01 | 10 | 5 | CERT-05 | integration | `uv run pytest tests/integration/test_preflight_doctor_integration.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — project definition with all deps, pytest/ruff/pyright config
- [ ] `src/ddk/__init__.py` — package init with `__version__`
- [ ] `tests/conftest.py` — shared fixtures (test_config, sample model factories)
- [ ] `tests/unit/` — unit test directory
- [ ] `tests/integration/` — integration test directory
- [ ] `tests/contract/` — contract test directory
- [ ] `tests/fakes/` — fake implementation tests directory
- [ ] Ruff config: `[tool.ruff]` in pyproject.toml
- [ ] Pyright config: `[tool.pyright]` in pyproject.toml
- [ ] pytest config: `asyncio_mode = "auto"`, warning filters for Pydantic V1 deprecation

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `ddk doctor` visual output | CERT-05 | Rich table formatting requires visual inspection | Run `uv run ddk doctor`, verify pass/fail table renders correctly |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

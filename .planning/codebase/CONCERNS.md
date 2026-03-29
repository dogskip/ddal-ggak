# Codebase Concerns

**Analysis Date:** 2024-12-19

## Tech Debt

### Pillow Type Stubs Workaround

**Issue:** Pillow `Image.resize()` method returns `Image` but stubs declare `Unknown` type, causing partial type loss.

**Files:** `src/ddk/adapters/screenshot_diff_local.py` (lines 28, 43)

**Impact:** Type checker shows `reportUnknownMemberType` despite using `# pyright: ignore` — reduces type safety guarantees for visual regression pipeline. Two workarounds in place (lines 28 and 43).

**Fix approach:** Monitor Pillow releases for type stub improvements. Consider switching to `Pillow-stubs` package if released. Current workaround is safe but indicates gap in Pillow's type coverage.

---

### LangGraph Optional[RunnableConfig] Union Syntax

**Issue:** LangGraph requires `Optional[RunnableConfig]` (not `RunnableConfig | None`) for KWARGS_CONFIG_KEYS compatibility across LangGraph versions.

**Files:** `src/ddk/graph/nodes/_wrapper.py` (lines 24, 66)

**Impact:** Using Python 3.10+ `|` syntax triggers `# noqa: UP045` (Ruff lint exemption). Code follows older typing conventions to maintain LangGraph compatibility, reducing code modernization.

**Fix approach:** Upgrade to LangGraph >=1.2.0 that supports modern union syntax. Current approach is defensive for version compatibility.

---

### Dynamic Import + Cast in Pipeline Runner

**Issue:** Runtime module lookup uses `import_module()` + `cast()` to retrieve `build_ddk_graph` function at runtime.

**Files:** `src/ddk/services/pipeline_runner.py` (lines 72-73)

**Impact:** Bypasses static type checking. Function is retrieved from `__dict__` and cast to `Callable[[], Any]` to suppress `pyright unknown-type`. If graph builder is renamed/moved, runtime will fail with `KeyError`.

**Fix approach:** This is necessary for LangGraph compiled graph serialization (graph is built at runtime, not import time). Add runtime validation: check for `KeyError` and provide clear error message. Consider registry pattern if multiple graphs are needed.

---

### SSIM Threshold 0.92 — Unvalidated Assumption

**Issue:** Screenshot similarity threshold hardcoded to 0.92 (85% pixel similarity) — is an unvalidated assumption based on gut estimate, not empirical calibration.

**Files:**
- `src/ddk/models/config.py` (line 31) — config default
- `src/ddk/models/visual.py` (threshold field) — visual report contract
- `src/ddk/services/runtime_validator.py` (line 13) — _SSIM_THRESHOLD constant

**Impact:** Visual regression gates may be too strict (false positives = forced rollback) or too lenient (missing real regressions). Affects Phase 4 autofix retry loop — incorrect threshold wastes LLM calls or passes broken changes.

**Trigger:** To calibrate: collect 20+ screenshot pairs from real projects, measure SSIM scores, compare against manual pass/fail judgement.

**Fix approach:**
1. Run visual regression pipeline on diverse projects (React, Vue, Svelte)
2. Plot SSIM distribution for human-approved layouts vs. regressions
3. Use ROC analysis to find optimal threshold (target: ~95% precision)
4. Document threshold decision with dataset reference
5. Consider threshold per project type (mobile vs. desktop layouts differ)

**Priority:** High — affects release gate reliability

---

### Anthropic SDK Version Constraint Too Loose

**Issue:** Dependency pins `anthropic>=0.40.0` with no upper bound. SDK API surface changes frequently.

**Files:** `pyproject.toml` (line 18)

**Impact:** Major SDK version updates may introduce breaking API changes. Known risk: OpenAI SDK v2 `beta.chat.completions.parse()` path — if Anthropic SDK v2 introduces similar beta namespaces, code breaks silently.

**Fix approach:** Pin to tested range: `anthropic>=0.40.0,<1.0.0` (or specific patch version after validation). Add integration test that verifies `messages.create(**kwargs)` signature.

**Priority:** Medium — detected in STATE.md as research item

---

## Known Issues / Research Items

### OpenAI SDK v2 Beta Path Unverified

**Issue:** Code references `OpenAI` as optional provider but SDK v2 path `beta.chat.completions.parse()` is untested.

**Files:** 
- `src/ddk/models/config.py` (lines 9-10) — LLMProvider enum includes OPENAI
- Implementation not yet written (OpenAI adapter doesn't exist)

**Trigger:** None in current codebase — OPENAI enum exists but no adapter implementation

**Workaround:** None — would fail at runtime if OPENAI provider selected

**Fix approach:** Implement OpenAI adapter validating `beta.chat.completions.parse()` API path. Cross-check against latest SDK changelog.

---

### Concurrency / Async Cleanup Gaps

**Issue:** Subprocess and worktree operations are async-based but cleanup is not guaranteed if graph execution crashes.

**Files:** 
- `src/ddk/adapters/local_git.py` (worktree create/remove at lines 48-61)
- `src/ddk/adapters/subprocess_build_runner.py` (process spawning)

**Impact:** If graph fails mid-execution, git worktrees may be orphaned on disk, wasting space. Subprocess pipes may leak if timeout is hit during `asyncio.wait_for()`.

**Fix approach:** Implement context managers for worktree lifecycle + subprocess resource cleanup. Use try/finally in nodes to guarantee rollback call even on exception.

**Priority:** Medium — affects long-running deployments

---

## Fragile Areas

### State Dictionary Access Without Type Guards

**Issue:** Graph nodes access state dict using `.get()` and `cast()` without runtime type validation.

**Files:**
- `src/ddk/graph/nodes/autofix.py` (lines 46, 52, 55, 57) — multiple casts
- `src/ddk/graph/router.py` (lines extracting state fields)

**Pattern:**
```python
report = cast(RuntimeValidationReport | None, state.get("runtime_validation_report"))
failure_hash_history = cast(list[int], state.get("failure_hash_history", []))
```

**Why fragile:** If upstream node forgets to populate `runtime_validation_report`, cast silently converts `None` to report type — type checker doesn't catch it. Runtime error occurs later when code tries to access report methods.

**Safe modification:** 
1. Validate state schema at graph entry point
2. Use Pydantic model for GraphState (not plain dict)
3. Or add runtime assertions: `assert isinstance(state.get(...), Expected), f"Missing {key}"`

**Test coverage gap:** No test validates that all required state fields are populated by dependent nodes.

---

### JSON Deserialization Without Schema Validation

**Issue:** Multiple service layers parse JSON from LLM responses / config files without strict schema validation.

**Files:**
- `src/ddk/services/generation_planner.py` (line ~80) — parses LLM JSON
- `src/ddk/services/output_normalizer.py` (line ~150) — normalizer output
- `src/ddk/installer.py` (lines 50-60) — MCP config parsing

**Pattern:**
```python
data = json.loads(response.content)
# No validation — assumes LLM returned correct schema
```

**Impact:** Malformed LLM response crashes the entire pipeline mid-execution. No fallback or partial parsing.

**Safe modification:**
1. Use Pydantic model validation after JSON parse
2. Add try/except with fallback behavior
3. Log invalid responses for debugging

---

### Type Ignore Comments in Claude Adapter

**Issue:** Multiple `# type: ignore` suppressions in Anthropic SDK integration indicate incomplete type stubs.

**Files:** `src/ddk/adapters/llm/claude.py` (lines 49-61, 74, 88, etc.)

**Impact:** Type checker cannot verify response schema or error cases. If SDK updates message structure, type checker won't catch incompatibility.

**Pattern:**
```python
response: anthropic.types.Message = await self._client.messages.create(**kwargs)  # type: ignore[call-overload]
usage = response.usage  # type: ignore[reportUnknownMemberType]
```

**Fix approach:** Consider using Anthropic's generated type stubs or contribute to `anthropic-stubs` package. For now, document which SDK methods are partially typed.

---

### Missing Env Validation at Startup

**Issue:** Some configuration values (API keys, model names, thresholds) are not validated until first use.

**Files:** `src/ddk/models/config.py` — no validation in `DdalggakConfig`

**Impact:** If `anthropic_api_key` is missing, error occurs during first LLM call (expensive), not during config load.

**Fix approach:** Add validators in `DdalggakConfig` for required fields. Use Pydantic's `field_validator` to check API keys non-empty at startup.

---

## Scaling Limits

### Context Pack Builder MAX_FILES = 6 Hard Limit

**Issue:** Context window is capped at 6 files × 300 lines = 1800 lines total for LLM context.

**Files:** `src/ddk/services/context_pack_builder.py` (lines 22-23)

**Limit:** Large codebases (>10k lines) will always have `insufficient_context=True`.

**Scaling path:**
1. Measure actual LLM context usage across projects
2. Consider adaptive limits based on project size
3. Implement token-counting instead of line-counting
4. Use retrieval-augmented generation (RAG) for selective file inclusion

**Priority:** Medium — affects code generation quality for large projects

---

### Subprocess Timeout at 300 Seconds

**Issue:** All build operations have hard timeout of 300s (5 minutes).

**Files:** `src/ddk/models/config.py` (line 25), `src/ddk/adapters/subprocess_build_runner.py`

**Impact:** Projects with slow builds (monorepos, heavy compilation) will timeout and fail validation, forcing autofix retry.

**Scaling path:**
1. Make timeout configurable per project type
2. Implement progressive timeout backoff (5m → 7m → 10m on retry)
3. Add build parallelization detection

---

## Performance Bottlenecks

### Synchronous Git Operations in Async Graph

**Issue:** `LocalGitAdapter` uses GitPython (synchronous) even though called from async graph nodes.

**Files:** `src/ddk/adapters/local_git.py` (lines 15-46 — sync methods like `.status()`, `.diff()`, `.log()`)

**Cause:** GitPython doesn't have async API. Only worktree operations are async.

**Impact:** Blocks event loop during repo scan on large repos (100k+ files). If multiple cases run concurrently, git operations serialize.

**Improvement path:**
1. Benchmark `.status()` on large repos to find actual bottleneck
2. If <100ms, current design is acceptable
3. If >500ms, fork GitPython operations to thread pool: `loop.run_in_executor()`
4. Consider pure-Python git implementations (GitPython is slow for large repos)

---

### Design Studio Document Generation Sequential Calls

**Issue:** Design studio uses `asyncio.Semaphore(self._concurrency)` to limit concurrent LLM calls, but semaphore=1 is default.

**Files:** `src/ddk/design/generator.py` (line ~30)

**Impact:** Multiple design documents generated sequentially, blocking on each LLM call latency. Could be 3-5x faster with concurrency=3-5.

**Improvement path:**
1. Set concurrency=3 by default (test for rate limits)
2. Add concurrency config option
3. Measure actual latency savings vs. API rate limit errors

---

## Test Coverage Gaps

### Pillow Visual Regression Pipeline — No Integration Tests

**Issue:** `LocalScreenshotDiffAdapter` computes SSIM using Pillow histogram method (not scikit-image). No integration tests verify SSIM scores against known image pairs.

**Files:** `src/ddk/adapters/screenshot_diff_local.py`

**What's not tested:** 
- SSIM score for identical images (should be 1.0)
- SSIM score for completely different images (should be near 0)
- SSIM calculation matches human perception of "good enough"

**Risk:** SSIM algorithm correctness is untested. If histogram-based method is wrong, threshold calibration will be invalid.

**Test approach:** Add parametrized test with known image pairs (e.g., same image vs. 50% noise added):
```python
@pytest.mark.parametrize("image_pair,expected_min_ssim", [
    ("identical", 0.99),
    ("10pct_noise", 0.85),
    ("50pct_noise", 0.30),
])
def test_ssim_scores_realistic(image_pair, expected_min_ssim):
    # Load test images from fixtures
    # Verify SSIM >= expected_min_ssim
```

---

### Playwright Browser Setup — Optional in Tests

**Issue:** Playwright integration tests skip if browser unavailable (`pytest.importorskip`, `pytest.skip`), but code paths using Playwright are not exercised in CI.

**Files:** `tests/integration/test_phase4_playwright.py` (pytest markers, skip conditionals)

**What's not tested:** 
- Browser screenshots on CI/Linux (runs locally on macOS only)
- Screenshot comparison accuracy under different rendering environments
- Chromium-specific rendering differences

**Risk:** Playwright integration may fail in production CI environment not tested locally.

**Fix approach:** Use pytest plugin to mock Playwright or use headless browser in Docker for CI.

---

### Exception Handling Paths — Incomplete Coverage

**Issue:** Graph nodes catch broad exceptions (`Exception`) and return error state, but error paths are not unit-tested.

**Files:** 
- `src/ddk/graph/nodes/_wrapper.py` (lines 86-90)
- Multiple service error handlers

**Pattern:**
```python
except Exception as exc:  # noqa: BLE001
    return {
        "terminal_state": "manual-review-required",
        "error_message": f"...: {exc}",
    }
```

**What's not tested:** 
- Does error state correctly terminate graph?
- Are error messages helpful for debugging?
- Do all exception types map to correct terminal state?

**Test approach:** Add parametrized test injecting failures:
```python
@pytest.mark.parametrize("exception", [OSError(), PermissionError(), RuntimeError()])
async def test_node_wrapper_exception_handling(exception):
    # Verify each exception type produces correct terminal_state
```

---

## Dependencies at Risk

### Ruff Linting Tool — Frequent Major Updates

**Issue:** `ruff>=0.5.0` is a fast-moving project. Major versions introduce breaking lint rule changes.

**Files:** `pyproject.toml` (line 31)

**Risk:** Future Ruff upgrade may flag new violations in existing code, breaking CI/linting step.

**Migration plan:**
1. Pin to minor version range: `ruff>=0.5.0,<0.8.0`
2. Before upgrading, run full lint check and review new violations
3. Update `pyproject.toml` lint rules if needed

---

### LangGraph 1.0+ API Surface Changes

**Issue:** LangGraph v1.0 was major release. Future v2.0 may introduce breaking changes to StateGraph, node registration, or config injection.

**Files:** Multiple graph node files depend on LangGraph internals

**Risk:** Upgrading LangGraph may require rewriting graph builder and node wrappers.

**Mitigation:** Version constraints in `pyproject.toml` currently allow `langgraph>=1.0.0` (no upper bound).

**Fix approach:** 
1. Pin to patch version after testing: `langgraph>=1.0.0,<2.0.0`
2. Subscribe to LangGraph changelog
3. Maintain compatibility shim for version-specific APIs

---

## Missing Critical Features

### No Observability / Structured Logging for LLM Calls

**Issue:** LLM calls are logged but not structured for cost analysis or debugging.

**Files:** `src/ddk/adapters/llm/claude.py` — logs cost but no structured metrics

**Blocks:** Cannot easily answer: "Which cases are exceeding $2.0 cost cap?" or "Why did LLM call fail?"

**Fix approach:** 
1. Add structured logging context (case_id, node, model, tokens, cost)
2. Export logs to JSON for downstream analysis
3. Add cost_cap enforcement at case level (not per-call)

---

### No Rate Limit Handling for Anthropic API

**Issue:** No exponential backoff or retry logic for Anthropic rate limit (429) responses.

**Files:** `src/ddk/adapters/llm/claude.py` — no retry logic

**Blocks:** If hitting rate limits, entire pipeline fails immediately instead of retrying.

**Fix approach:** Implement tenacity-based retry with exponential backoff for 429 responses.

---

## Security Considerations

### Sandbox Execution Security

**Risk:** Generated code is executed via subprocess in sandbox but there is no guarantee subprocess environment is truly isolated.

**Files:** `src/ddk/adapters/subprocess_build_runner.py`, `src/ddk/adapters/sandbox/`

**Current mitigation:** Subprocess inherits parent process environment but should not access secrets.

**Recommendations:**
1. Audit subprocess environment variables — ensure no AWS keys, API tokens inherited
2. Add sandbox environment whitelist (ENV_WHITELIST exists but verify exhaustiveness)
3. Test that subprocess cannot escape cwd or access parent fs

---

### LLM Context Information Leakage

**Risk:** LLM receives full source code context (repo scan) which may contain sensitive information (API keys in comments, internal design docs).

**Files:** `src/ddk/services/context_pack_builder.py` — includes arbitrary repo files

**Current mitigation:** Whitelist binary extensions, skip common secret files

**Recommendations:**
1. Add regex-based secret detection in context files before sending to LLM
2. Redact known secret patterns (AWS keys, JWT tokens, etc.)
3. Document risk: "LLM provider (Anthropic) will see your source code"

---

### API Key Management

**Risk:** `.env` files may contain secrets that get committed or leaked.

**Files:** `src/ddk/models/config.py` — config reads from `.env`

**Current mitigation:** `.gitignore` should exclude `.env`

**Recommendations:**
1. Add startup warning if `.env` exists in git repo
2. Require explicit env var setup for production (no `.env` fallback)
3. Scan for accidentally committed secrets in CI

---

## Priority Ranking

1. **High:** SSIM threshold calibration (affects visual regression gates)
2. **High:** State dictionary type safety (fragile autofix loop)
3. **Medium:** Anthropic SDK version pinning (prevents breaking changes)
4. **Medium:** JSON schema validation (robustness)
5. **Medium:** Async cleanup guarantees (long-running stability)
6. **Low:** Playwright CI coverage (functional but incomplete testing)
7. **Low:** Rate limit retry logic (graceful degradation)

---

*Concerns audit: 2024-12-19 — Phase 5 verified, v1.0 delivery pipeline complete*

# Phase 4: Validation & Self-Healing — Research

**Researched:** 2025-07-14
**Domain:** LangGraph conditional loops · git worktree sandbox · Playwright Python async · scikit-image SSIM · deterministic auto-fix patterns
**Confidence:** HIGH (all core findings verified against installed package source or official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### 자동화 수리 전략: 하이브리드
| 규칙 ID | 대상 Taxonomy | 구현 방식 |
|---------|--------------|----------|
| R-01 | FT-LINT-001 | 미사용 import 줄 삭제 (결정론적) |
| R-02 | FT-LINT-002/003 | eslint --fix 실행 (결정론적) |
| R-03 | FT-TYPE-002 | `: any` annotation 추가 (결정론적) |
| R-04 | FT-TYPE-001/003 | `as unknown as T` cast 삽입 (결정론적) |
| R-05 | FT-BUILD-003 | package.json dependencies 추가 (결정론적) |
| R-06 | FT-BUILD-001 | 상대경로 import 재작성 (결정론적) |
| R-07 | FT-RUNTIME-002 | Optional chaining `?.` 추가 (결정론적) |
| R-08 | FT-ASYNC-002 | `await` 누락 추가 (결정론적) |
| R-09 | FT-BUILD-002 / FT-RUNTIME-001 | LLM 재생성 (FakeLLM key: `"autofix"`) |

#### Playwright 통합 범위
- Phase 4 통합 테스트에서 **실제 Playwright + dev server** 기동
- FakePlaywrightAdapter는 단위 테스트에서만 사용
- CI skip: `pytest.mark.playwright` 마커

#### Validation-Fix 루프: LangGraph 조건부 엣지
```
START → ... → normalize → validate → [router]
    ├─ "pass"           → END
    ├─ "fix_available"  → autofix → validate (루프, budget 소모)
    └─ "exhausted"      → END (terminal_state="manual-review-required")
```
- oscillation 감지: `failure_set_hash = hash(frozenset(failure.id for failure in failures))`
- `retry_budget_remaining` 매 fix마다 차감

### the agent's Discretion
- SSIM 구현: scikit-image 또는 Pillow 기반 (threshold=0.92 고정)
- git worktree vs TempDirSandbox: 단위 테스트에선 TempDirSandbox, 통합 테스트에선 실제 worktree

### Deferred Ideas (OUT OF SCOPE)
- 실제 CI 환경 Playwright 자동 설치 (`playwright install chromium`)
- SSIM 기반 diff 이미지 생성 (시각적 리포트)
- 외부 lint 도구 자동 선택 (eslint vs biome vs oxc)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VALID-01 | git worktree 샌드박스에서 build/typecheck/lint/runtime smoke → RuntimeValidationReport | git worktree async subprocess; GitAdapter.create_worktree/remove_worktree protocol 확인 |
| VALID-02 | Playwright 브라우저 콘솔 + 네트워크 실패 수집, 상관 ID | playwright.async_api page.on('console') / page.on('requestfailed'); PlaywrightAdapter 프로토콜 신규 메서드 추가 |
| VALID-03 | 레퍼런스 vs 생성 스크린샷 SSIM (threshold=0.92) → VisualRegressionReport | scikit-image.metrics.structural_similarity(full=True); ScreenshotDiffAdapter.compute_ssim |
| VALID-04 | AutoFixPlanner + 9개 규칙, 최대 3회 재시도, 진동 감지 | 결정론적 정규식 패턴 도출; FakeLLM "autofix" 키; failure_hash_history 상태 필드 추가 |
| VALID-05 | FailureClassifier — 모든 실패를 FAILURE_TAXONOMY ID로 매핑 | validation.py FAILURE_TAXONOMY 20개 코드 재사용; 순수 Python 로직, I/O 없음 |
| VALID-07 | RollbackController — refs/ddk/fix/{case_id}/attempt-{n} checkpoint, 실패 시 롤백 | GitAdapter.create_checkpoint / rollback_to 프로토콜 확인; FakeRollbackController 존재 확인 |
</phase_requirements>

---

## Summary

Phase 4는 생성 파이프라인의 **검증 루프** 를 완성한다. 핵심은 세 층위: (1) 샌드박스에서의 기술적 검증(빌드/타입/린트/런타임), (2) Playwright 브라우저 검증 + SSIM 비주얼 회귀, (3) LangGraph 조건부 백엣지 루프를 통한 자동 수리.

LangGraph 1.1.3(`add_conditional_edges` + `config={'recursion_limit': N}`)이 이미 설치되어 있고, 백엣지 루프는 직접 코드로 검증했다. `GraphRecursionError`는 `langgraph.errors`에서 import한다. **playwright, scikit-image, Pillow, numpy 4개 패키지는 현재 venv에 없어 pyproject.toml에 추가가 필수**다.

서비스 구현 권장 순서: FailureClassifier(순수 로직) → RollbackController(GitAdapter 래핑) → RuntimeValidator(sandbox 오케스트레이션) → AutoFixPlanner(hybrid patch) → validate/autofix 노드(thin adapter) → builder.py 그래프 확장.

**Primary recommendation:** LangGraph 백엣지 루프를 먼저 작성해 연결 구조를 확정한 뒤, 각 서비스를 TDD 방식으로 아래에서 위로 채운다.

---

## Standard Stack

### New Dependencies Required

| Library | Version | Purpose | Status |
|---------|---------|---------|--------|
| scikit-image | ≥0.21 | SSIM 계산 (`skimage.metrics.structural_similarity`) | **미설치 — 추가 필수** |
| Pillow | ≥10.0 | 이미지 파일 읽기 (PIL.Image → numpy array) | **미설치 — 추가 필수** |
| numpy | ≥1.26 | scikit-image가 요구하는 array 연산 | **미설치 (scikit-image 의존성으로 자동 설치됨)** |
| playwright | ≥1.44 | 실제 브라우저 자동화 (통합 테스트용) | **미설치 — 추가 필수** |
| pytest-playwright | ≥0.5 | playwright pytest 픽스처 + `playwright` 마커 | **미설치 — dev dep 추가 필수** |

### Already Installed (reuse)

| Library | Verified Version | Role in Phase 4 |
|---------|-----------------|----------------|
| langgraph | 1.1.3 | 조건부 엣지 + 백엣지 루프 |
| langgraph-checkpoint | (bundled) | 상태 체크포인트 |
| pydantic v2 | ≥2.7 | 기존 모델 재사용 |
| pytest-asyncio | ≥0.23 (asyncio_mode=auto) | 비동기 서비스 테스트 |
| gitpython | ≥3.1.40 | GitAdapter 읽기 연산 |

**Installation (add to pyproject.toml):**
```toml
[project.dependencies]
# 기존 deps에 추가
"scikit-image>=0.21.0",
"Pillow>=10.0.0",
"playwright>=1.44.0",

[project.optional-dependencies]
dev = [
    # 기존 dev deps에 추가
    "pytest-playwright>=0.5.0",
]
```

```bash
uv add scikit-image Pillow playwright
uv add --dev pytest-playwright
playwright install chromium  # 브라우저 바이너리 설치 (CI 제외)
```

---

## Architecture Patterns

### Phase 4 신규 파일 레이아웃
```
src/ddk/
├── services/
│   ├── runtime_validator.py     # VALID-01~03: sandbox 오케스트레이션
│   ├── failure_classifier.py    # VALID-05: FAILURE_TAXONOMY 매핑 (순수 로직)
│   ├── auto_fix_planner.py      # VALID-04: 9개 규칙 hybrid patch
│   └── rollback_controller.py   # VALID-07: git checkpoint 관리
├── graph/
│   ├── nodes/
│   │   ├── validate.py          # thin adapter → RuntimeValidator
│   │   └── autofix.py           # thin adapter → AutoFixPlanner
│   └── router.py                # route_after_validate() 함수
└── adapters/
    └── playwright_browser.py    # FailedRequestEntry 추가 (additive)

tests/
└── unit/
    └── phase4/
        ├── __init__.py
        ├── test_runtime_validator.py
        ├── test_failure_classifier.py
        ├── test_auto_fix_planner.py
        ├── test_rollback_controller.py
        ├── test_validate_node.py
        ├── test_autofix_node.py
        └── test_router.py
```

### Pattern 1: LangGraph 조건부 백엣지 루프

**검증된 API** (`langgraph==1.1.3`, 직접 실행 확인):

```python
# Source: 직접 실행 검증 (2025-07-14)
from typing import Literal
from langgraph.graph import StateGraph, END, START
from langgraph.errors import GraphRecursionError

def route_after_validate(state: GraphState) -> Literal["fix_available", "exhausted"]:
    """router.py에 위치. PURE FUNCTION — side effect 없음."""
    report = state.get("runtime_validation_report")
    if report is None or (report.build_success and report.type_check_success and report.lint_success):
        # visual 회귀도 통과?
        vis = state.get("visual_regression_report")
        if vis is None or vis.pass_result:
            return "pass"  # → END

    # budget 소진
    if state.get("retry_budget_remaining", 0) <= 0:
        return "exhausted"  # → END (manual-review)

    # oscillation 감지
    failures = report.failures if report else []
    cur_hash = hash(frozenset(f.id for f in failures))
    seen = state.get("failure_hash_history", [])
    if cur_hash in seen:
        return "exhausted"  # A→B→A 루프 탈출

    return "fix_available"  # → autofix → validate 루프


# builder.py 확장 (normalize 이후)
workflow.add_node("validate", node_wrapper(validate_node))
workflow.add_node("autofix", node_wrapper(autofix_node))

workflow.add_edge("normalize", "validate")
workflow.add_conditional_edges(
    "validate",
    route_after_validate,
    {
        "pass": END,
        "fix_available": "autofix",
        "exhausted": END,
    },
)
workflow.add_edge("autofix", "validate")  # ← 백엣지

# 호출 시: recursion_limit은 최대 반복 * 노드 수 기준
# 3회 retry × 2노드(validate+autofix) + normalize + 여유 = 25
result = await graph.ainvoke(state, config={"recursion_limit": 25}, context=container)
```

**`GraphRecursionError` 안전망:** `recursion_limit`이 실제 루프 상한보다 넉넉하면 정상 동작. budget + oscillation으로 먼저 탈출하므로 `GraphRecursionError`는 예기치 못한 버그 신호로만 사용.

**GraphState 신규 필드 (additive-only):**
```python
# state.py에 추가 — 기존 필드 변경 없음
failure_hash_history: list[int]   # oscillation 감지용 해시 이력
```
`initial_state()` 팩토리에도 `failure_hash_history=[]` 추가.

### Pattern 2: validate 노드 (thin adapter)

```python
# src/ddk/graph/nodes/validate.py
async def validate_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Thin adapter: state → RuntimeValidator → state. No business logic."""
    container: ServiceContainer | None = kwargs.get("context")
    validator = RuntimeValidator(
        sandbox=container.sandbox,
        build_runner=container.build_runner,
        playwright=container.browser,
        screenshot_diff=container.screenshot_diff,
        git=container.git,
    )
    report, vis_report = await validator.run(state)

    failures = report.failures if report else []
    cur_hash = hash(frozenset(f.id for f in failures))
    seen = list(state.get("failure_hash_history", []))

    return {
        "runtime_validation_report": report,
        "visual_regression_report": vis_report,
        "current_node": "validate",
        "failure_hash_history": seen + [cur_hash],
    }
```

### Pattern 3: autofix 노드 (thin adapter)

```python
# src/ddk/graph/nodes/autofix.py
async def autofix_node(state: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    """Thin adapter: state → AutoFixPlanner → state."""
    container: ServiceContainer | None = kwargs.get("context")
    planner = AutoFixPlanner(llm=container.llm)

    report = state["runtime_validation_report"]
    attempt_n = len(state.get("fix_attempts", [])) + 1

    fix_attempt, patched_artifacts = await planner.plan_and_apply(
        failures=report.failures,
        artifacts=state["generated_artifacts"],
        case_id=state["case_id"],
        attempt_number=attempt_n,
    )

    return {
        "generated_artifacts": patched_artifacts,
        "fix_attempts": state["fix_attempts"] + [fix_attempt],
        "retry_budget_remaining": state["retry_budget_remaining"] - 1,
        "current_node": "autofix",
    }
```

### Pattern 4: git worktree 샌드박스 (VALID-01)

GitAdapter 프로토콜이 `create_worktree` / `remove_worktree` / `create_checkpoint` / `rollback_to`를 이미 정의함. 실제 구현은 `asyncio.create_subprocess_exec` (D-04 "write ops = subprocess" 원칙):

```python
# src/ddk/adapters/git_impl.py (신규 실제 구현)
import asyncio
from pathlib import Path

class GitSubprocessAdapter:
    """D-04: write ops use subprocess, read ops use GitPython."""

    async def create_worktree(self, repo_path: Path, worktree_path: Path, branch: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "add", "--detach", str(worktree_path),
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {stderr.decode()}")

    async def remove_worktree(self, repo_path: Path, worktree_path: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "remove", "--force", str(worktree_path),
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        # force remove: ignore returncode (path may not exist)

    async def create_checkpoint(self, repo_path: Path, ref_name: str) -> str:
        # refs/ddk/fix/{case_id}/attempt-{n} 형식
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "HEAD",
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        head_sha = stdout.decode().strip()

        proc2 = await asyncio.create_subprocess_exec(
            "git", "update-ref", ref_name, head_sha,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()
        return head_sha

    async def rollback_to(self, repo_path: Path, ref_name: str) -> None:
        proc = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", ref_name,
            cwd=str(repo_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git reset failed: {stderr.decode()}")
```

### Pattern 5: SSIM 계산 (VALID-03)

scikit-image `structural_similarity` API — `full=True`로 픽셀별 diff 맵 획득:

```python
# src/ddk/adapters/screenshot_diff_impl.py
import numpy as np
from pathlib import Path
from PIL import Image
from skimage.metrics import structural_similarity  # scikit-image>=0.19

from ddk.adapters.screenshot_diff import SSIMResult

class ScikitSSIMAdapter:
    """ScreenshotDiffAdapter 구현."""

    def compute_ssim(self, reference: Path, generated: Path) -> SSIMResult:
        ref_arr = np.array(Image.open(reference).convert("RGB"))
        gen_arr = np.array(Image.open(generated).convert("RGB"))

        # 크기 불일치 시 resize (generated를 reference 크기로)
        if ref_arr.shape != gen_arr.shape:
            ref_h, ref_w = ref_arr.shape[:2]
            gen_pil = Image.open(generated).convert("RGB").resize((ref_w, ref_h))
            gen_arr = np.array(gen_pil)

        score, diff_map = structural_similarity(
            ref_arr,
            gen_arr,
            channel_axis=2,      # RGB channels
            data_range=255,
            full=True,           # full=True → diff_map 반환
        )

        # mismatch regions: diff < 0.5 (significant difference)
        mismatch_mask = diff_map.mean(axis=2) < 0.5
        regions = self._find_bounding_boxes(mismatch_mask)

        return SSIMResult(
            score=float(score),
            mismatch_regions=regions,
            diff_image_path=None,
        )

    def _find_bounding_boxes(self, mask: np.ndarray) -> list[dict[str, int]]:
        """Simple row/col bounding box from boolean mask."""
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any():
            return []
        rmin, rmax = int(np.where(rows)[0][[0, -1]])
        cmin, cmax = int(np.where(cols)[0][[0, -1]])
        return [{"x": cmin, "y": rmin, "width": cmax - cmin, "height": rmax - rmin}]

    def generate_diff_image(self, reference: Path, generated: Path, output: Path) -> Path:
        # Deferred (Phase 5) — 현재는 NotImplementedError
        raise NotImplementedError("diff image generation deferred to Phase 5")
```

**API 확인:** `skimage.metrics.structural_similarity(im1, im2, channel_axis=2, data_range=255, full=True)` — `channel_axis` 파라미터가 0.19에서 추가됨 (`multichannel` deprecated). ≥0.21 기준.

### Pattern 6: Playwright async (VALID-02)

현재 `PlaywrightAdapter` 프로토콜에 `get_failed_requests`가 없음. **Additive 추가** 필요:

```python
# src/ddk/adapters/playwright_browser.py — additive 추가
from dataclasses import dataclass

@dataclass
class FailedRequestEntry:
    """Network request failure."""
    url: str
    failure_text: str   # playwright request.failure().error_text
    correlation_id: str | None = None
```

```python
# 실제 Playwright 구현 (통합 테스트)
from playwright.async_api import async_playwright, ConsoleMessage, Request

class RealPlaywrightAdapter:
    """실제 Playwright 브라우저 자동화 구현."""

    async def capture_screenshot(self, url: str, output_path: Path,
                                  viewport: tuple[int, int] = (1280, 800)) -> Path:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
            await page.goto(url, wait_until="networkidle")
            await page.screenshot(path=str(output_path))
            await browser.close()
        return output_path

    async def get_console_errors(self, url: str, wait_ms: int = 5000) -> list[ConsoleEntry]:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            errors: list[ConsoleEntry] = []

            def on_console(msg: ConsoleMessage) -> None:
                if msg.type in ("error", "warn"):
                    errors.append(ConsoleEntry(
                        level=msg.type,
                        message=msg.text,
                        url=msg.location.get("url") if msg.location else None,
                        line_number=msg.location.get("lineNumber") if msg.location else None,
                    ))

            page.on("console", on_console)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(wait_ms)
            await browser.close()
        return errors

    async def get_failed_requests(self, url: str, wait_ms: int = 5000,
                                   correlation_id: str | None = None) -> list[FailedRequestEntry]:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            failed: list[FailedRequestEntry] = []

            def on_request_failed(request: Request) -> None:
                failure = request.failure  # Returns str | None
                failed.append(FailedRequestEntry(
                    url=request.url,
                    failure_text=failure or "unknown",
                    correlation_id=correlation_id,
                ))

            page.on("requestfailed", on_request_failed)
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(wait_ms)
            await browser.close()
        return failed

    async def close(self) -> None:
        pass  # context manager handles cleanup
```

**pytest.mark.playwright 마커 등록** (pyproject.toml):
```toml
[tool.pytest.ini_options]
markers = [
    "integration: real API calls — requires ANTHROPIC_API_KEY",
    "playwright: requires Playwright + browser binaries (skip in CI)",  # ← 추가
]
```

### Pattern 7: AutoFixPlanner 9개 규칙

각 규칙의 결정론적 패턴:

```python
# src/ddk/services/auto_fix_planner.py
import re
from pathlib import Path

# R-01: FT-LINT-001 — 미사용 import 줄 삭제
# eslint/tsc 오류 메시지에서 파일 경로 + "is defined but never used" 파싱
def r01_remove_unused_import(content: str, symbol: str) -> str:
    """Remove import line containing the unused symbol."""
    # import { Foo, Bar } → import { Bar } (symbol=Foo)
    # 완전 삭제 패턴: import { Foo } from '...'
    pattern = rf"^import\s+\{{[^}}]*\b{re.escape(symbol)}\b[^}}]*\}}\s+from\s+['\"][^'\"]+['\"];\s*$"
    lines = [l for l in content.splitlines(keepends=True)
             if not re.match(pattern, l)]
    return "".join(lines)

# R-02: FT-LINT-002/003 — eslint --fix (subprocess)
async def r02_eslint_fix(file_path: Path, cwd: Path) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "npx", "eslint", "--fix", str(file_path.relative_to(cwd)),
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, _ = await proc.communicate()
    return proc.returncode == 0

# R-03: FT-TYPE-002 — `: any` annotation 추가
def r03_add_any_annotation(content: str, symbol: str) -> str:
    """Add ': any' to function param or variable lacking type annotation."""
    # function foo(bar) → function foo(bar: any)
    pattern = rf"\b({re.escape(symbol)})\s*(?=[,\)])"
    return re.sub(pattern, r"\1: any", content, count=1)

# R-04: FT-TYPE-001/003 — `as unknown as T` cast
def r04_add_cast(content: str, expression: str, target_type: str) -> str:
    """Wrap expression with (expr as unknown as TargetType)."""
    escaped = re.escape(expression)
    return re.sub(escaped, f"({expression} as unknown as {target_type})", content, count=1)

# R-05: FT-BUILD-003 — package.json dependency 추가
import json
def r05_add_dependency(pkg_json_content: str, package_name: str, version: str = "latest") -> str:
    data = json.loads(pkg_json_content)
    data.setdefault("dependencies", {})[package_name] = version
    return json.dumps(data, indent=2)

# R-06: FT-BUILD-001 — 상대경로 import 재작성
def r06_fix_relative_import(content: str, wrong_path: str, correct_path: str) -> str:
    """Replace wrong import path with correct relative path."""
    pattern = rf"(from\s+['\"]){re.escape(wrong_path)}(['\"])"
    return re.sub(pattern, rf"\g<1>{correct_path}\g<2>", content)

# R-07: FT-RUNTIME-002 — Optional chaining 추가
def r07_add_optional_chaining(content: str, expr: str) -> str:
    """foo.bar → foo?.bar for null reference."""
    # a.b.c → a?.b?.c
    parts = expr.split(".")
    if len(parts) < 2:
        return content
    chained = "?.".join(parts)
    return content.replace(expr, chained, 1)

# R-08: FT-ASYNC-002 — await 추가
def r08_add_await(content: str, call_expr: str) -> str:
    """Add await before async call expression."""
    return content.replace(call_expr, f"await {call_expr}", 1)

# R-09: FT-BUILD-002/FT-RUNTIME-001 — LLM 재생성
# FakeLLM key: "autofix" (system prompt starts with "Autofix")
_AUTOFIX_SYSTEM_PROMPT = """\
Autofix the following TypeScript/JavaScript source file.
The file has the following error(s). Regenerate the file fixing ONLY the listed errors.
Respond with the complete fixed file content only — no markdown fences.
"""
```

### Pattern 8: FailureClassifier (순수 로직)

```python
# src/ddk/services/failure_classifier.py
from ddk.models.validation import FAILURE_TAXONOMY, FailureRecord

# 분류 규칙: 오류 메시지 패턴 → taxonomy ID
_CLASSIFIER_RULES: list[tuple[str, str, str]] = [
    # (패턴, taxonomy_id, severity)
    (r"Cannot find module|Module not found", "FT-BUILD-001", "critical"),
    (r"SyntaxError|Unexpected token|Unexpected end", "FT-BUILD-002", "critical"),
    (r"Cannot find name|is not assignable to type", "FT-TYPE-001", "major"),
    (r"implicitly has an 'any' type|lacks return-type", "FT-TYPE-002", "minor"),
    (r"is not a module|has no exported member", "FT-BUILD-003", "major"),
    (r"Unused variable|is defined but never used", "FT-LINT-001", "minor"),
    (r"Expected.*got|Parsing error", "FT-LINT-002", "minor"),
    (r"Uncaught TypeError|Cannot read propert", "FT-RUNTIME-002", "critical"),
    (r"Unhandled.*rejection|UnhandledPromise", "FT-RUNTIME-001", "critical"),
    (r"404|Failed to fetch|net::ERR", "FT-RUNTIME-003", "major"),
    (r"Layout shift|CLS", "FT-VISUAL-001", "major"),
    (r"await.*not.*async|async.*missing", "FT-ASYNC-002", "major"),
]

class FailureClassifier:
    """Maps raw error strings to FAILURE_TAXONOMY IDs. No I/O."""

    def classify(self, raw_message: str, file_path: str | None = None) -> FailureRecord:
        import re, uuid
        for pattern, taxonomy_id, severity in _CLASSIFIER_RULES:
            if re.search(pattern, raw_message, re.IGNORECASE):
                return FailureRecord(
                    id=str(uuid.uuid4()),
                    taxonomy_id=taxonomy_id,
                    severity=severity,  # type: ignore[arg-type]
                    message=raw_message[:500],
                    file_path=file_path,
                    raw_output=raw_message,
                )
        # fallback
        return FailureRecord(
            id=str(uuid.uuid4()),
            taxonomy_id="FT-RUNTIME-001",
            severity="major",
            message=raw_message[:500],
            file_path=file_path,
            raw_output=raw_message,
        )
```

### Anti-Patterns to Avoid

- **back-edge 없이 `add_edge("autofix", END)`**: 루프가 안 생김. `add_edge("autofix", "validate")`로 백엣지 필수.
- **budget 차감을 validate 노드에서**: 항상 autofix 노드에서만 차감. validate는 읽기 전용 리포트 생성.
- **oscillation hash를 `FailureRecord.taxonomy_id`로**: 동일 분류 ≠ 동일 failure. `failure.id` (UUID)의 frozenset이어야 함 — 단, UUID는 매번 다르게 생성되므로 hash는 **taxonomy_id + file_path 조합**으로 안정적으로 계산해야 한다.

  **수정 권장:**
  ```python
  cur_hash = hash(frozenset(
      (f.taxonomy_id, f.file_path or "") for f in failures
  ))
  ```
  UUID 기반이면 동일한 오류도 매번 다른 hash → oscillation 미탐지.

- **`asyncio.subprocess.run` 블로킹 사용**: `create_subprocess_exec`으로 비동기 실행.
- **scikit-image `multichannel=True`**: 0.19에서 deprecated, 0.21에서 제거. `channel_axis=2` 사용.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SSIM 계산 | 직접 픽셀 비교 루프 | `skimage.metrics.structural_similarity` | Gaussian filter, luminance/contrast/structure 가중치, 업계 표준 |
| 이미지 로딩/resize | PIL.Image 직접 구현 | `PIL.Image.open(...).convert("RGB").resize(...)` | 포맷 호환성 (PNG/JPEG/WebP) |
| 브라우저 자동화 | requests + BeautifulSoup | `playwright.async_api` | JS 실행, 콘솔 이벤트, 네트워크 인터셉트 |
| git worktree 관리 | shutil.copytree sandbox | `git worktree add --detach` | git 이력 보존, 빠른 생성, 클린 상태 보장 |
| recursion guard | 수동 counter 필드 | `config={'recursion_limit': N}` + `GraphRecursionError` | LangGraph 내장 안전망 |

---

## Runtime State Inventory

> Phase 4는 신규 서비스 구현이고, 기존 런타임 상태를 rename/마이그레이션하지 않음. 해당 사항 없음.

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — Phase 4는 신규 구현 | — |
| Live service config | None | — |
| OS-registered state | None | — |
| Secrets/env vars | None (LLM key는 기존 ANTHROPIC_API_KEY 재사용) | — |
| Build artifacts | None | — |

---

## Common Pitfalls

### Pitfall 1: oscillation hash 불안정 (UUID 기반)
**What goes wrong:** `FailureRecord.id`가 UUID라면 동일 오류도 매번 다른 hash → 영원히 루프.
**Why it happens:** CONTEXT.md 원문 `hash(frozenset(failure.id for f in failures))` → `failure.id`는 UUID.
**How to avoid:** hash 계산 시 `(taxonomy_id, file_path)` 튜플 사용:
```python
cur_hash = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in failures))
```
**Warning signs:** retry loop이 budget 소진까지 같은 오류를 반복하지만 oscillation으로 탈출 안 됨.

### Pitfall 2: Playwright `request.failure` 속성 타입
**What goes wrong:** `request.failure` 반환값은 버전별로 다름.
**Why it happens:** `playwright>=1.44`에서 `request.failure` 속성은 `str | None` (failure error text). 이전 버전은 `.failure()` 메서드였음.
**How to avoid:** `playwright>=1.44` 고정. `request.failure` (property). pyright로 타입 확인.

### Pitfall 3: SSIM 이미지 크기 불일치
**What goes wrong:** reference(1280×800)와 generated(1280×801)가 다르면 `structural_similarity` 예외.
**Why it happens:** dev server에서 스크롤바, DPR 차이로 픽셀 1개 차이 발생.
**How to avoid:** `compute_ssim`에서 generated를 reference 크기로 리사이즈 후 비교. 크기 차이는 `VisualRegressionReport`에 로그.

### Pitfall 4: `recursion_limit` 과소 설정
**What goes wrong:** `GraphRecursionError` 발생 — `terminal_state`가 `manual-review-required`가 아닌 예외로 처리됨.
**Why it happens:** 3 retries × (validate + autofix) = 6 step + normalize + intake + ... = 최소 10+.
**How to avoid:** 안전 마진 포함 25로 설정. budget이 먼저 소진되므로 정상 경로에서 절대 도달 안 함.

### Pitfall 5: `node_wrapper` 안 통한 노드 등록
**What goes wrong:** `ServiceContainer` DI가 동작 안 함 (context=None).
**Why it happens:** `workflow.add_node("validate", validate_node)` — wrapper 없음.
**How to avoid:** 기존 패턴과 동일: `workflow.add_node("validate", node_wrapper(validate_node))`.

### Pitfall 6: autofix가 `generated_artifacts` None으로 패치 시도
**What goes wrong:** autofix 노드가 state에서 `generated_artifacts`를 읽었을 때 None.
**Why it happens:** validate 노드가 실패해서 artifacts를 수정하지 않은 경우.
**How to avoid:** autofix 노드 초반에 None 가드 추가. None이면 `terminal_state="manual-review-required"` 반환.

---

## Implementation Order (권장)

```
Wave 0 (테스트 인프라):
  1. tests/unit/phase4/__init__.py 생성
  2. pytest.mark.playwright 마커 pyproject.toml 등록
  3. conftest.py에 phase4 픽스처 추가 (fake_git_adapter, fake_build_runner)

Wave 1 (순수 로직 — 의존성 없음):
  4. FailureClassifier → tests/unit/phase4/test_failure_classifier.py

Wave 2 (어댑터 구현):
  5. GitSubprocessAdapter (RollbackController용)
  6. ScikitSSIMAdapter (SSIM)
  7. RealPlaywrightAdapter (통합 테스트 전용)

Wave 3 (서비스):
  8. RollbackController → tests/unit/phase4/test_rollback_controller.py
  9. RuntimeValidator → tests/unit/phase4/test_runtime_validator.py
  10. AutoFixPlanner → tests/unit/phase4/test_auto_fix_planner.py

Wave 4 (그래프 통합):
  11. router.py (route_after_validate)
  12. validate 노드 + autofix 노드
  13. state.py: failure_hash_history 필드 추가
  14. builder.py: 노드/엣지 추가
  15. ServiceContainer: 4개 신규 서비스 필드 추가

Wave 5 (패키지 설치 + 통합 테스트):
  16. uv add scikit-image Pillow playwright; uv add --dev pytest-playwright
  17. playwright install chromium
  18. tests/integration/test_validation_pipeline.py
```

---

## Code Examples

### validate 루프 전체 흐름 (검증된 패턴)

```python
# Source: 직접 실행 검증 2025-07-14 (langgraph==1.1.3)
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from typing import Literal

def route_after_validate(state: GraphState) -> Literal["pass", "fix_available", "exhausted"]:
    report = state.get("runtime_validation_report")
    if _all_passing(state):
        return "pass"
    if state.get("retry_budget_remaining", 0) <= 0:
        return "exhausted"
    failures = report.failures if report else []
    cur_hash = hash(frozenset((f.taxonomy_id, f.file_path or "") for f in failures))
    if cur_hash in state.get("failure_hash_history", []):
        return "exhausted"
    return "fix_available"

workflow.add_conditional_edges(
    "validate",
    route_after_validate,
    {"pass": END, "fix_available": "autofix", "exhausted": END},
)
workflow.add_edge("autofix", "validate")  # back-edge

# invoke
result = await graph.ainvoke(state, config={"recursion_limit": 25}, context=container)
```

### TDD 픽스처 패턴

```python
# tests/unit/phase4/test_runtime_validator.py
import pytest
from tests.fakes import TempDirSandbox, FakePlaywrightAdapter
from ddk.services.runtime_validator import RuntimeValidator

@pytest.fixture
def validator(tmp_path):
    return RuntimeValidator(
        sandbox=TempDirSandbox(),
        build_runner=FakeBuildRunner(success=True),
        playwright=FakePlaywrightAdapter(console_errors=[]),
        screenshot_diff=FakeSSIMAdapter(score=0.95),
        git=FakeGitAdapter(),
    )

async def test_build_failure_produces_critical_record(validator, tmp_path):
    # Red: stub returns empty report
    # Green: build_runner returncode=1 → FT-BUILD-001 FailureRecord
    fake_runner = FakeBuildRunner(success=False, stderr="Cannot find module './Button'")
    v = RuntimeValidator(sandbox=TempDirSandbox(), build_runner=fake_runner, ...)
    report, _ = await v.run(mock_state_with_artifacts(tmp_path))
    assert not report.build_success
    assert any(f.taxonomy_id == "FT-BUILD-001" for f in report.failures)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `compare_ssim` | `structural_similarity` | scikit-image 0.19 | import 경로 변경 |
| `multichannel=True` | `channel_axis=2` | scikit-image 0.19 | 파라미터명 변경 |
| `playwright.sync_api` | `playwright.async_api` | playwright-python 1.x | asyncio 통합 |
| `request.failure()` (method) | `request.failure` (property str\|None) | playwright-python ~1.20 | 속성 접근으로 변경 |
| LangGraph `__END__` | `END` (import from langgraph.graph) | langgraph 0.1+ | 상수 이름 변경 |

---

## Open Questions

1. **FakePlaywrightAdapter에 `get_failed_requests` 추가 필요**
   - 현재 FakePlaywrightAdapter는 `get_console_errors`만 있고 `get_failed_requests`가 없음
   - `PlaywrightAdapter` 프로토콜 확장 + FakePlaywrightAdapter 확장 필요
   - 권장: `failed_requests: list[FailedRequestEntry] = []` 생성자 파라미터 추가

2. **`FakeBuildRunner`가 없음**
   - `FakeSubprocessRunner`는 있지만 `BuildRunner` 프로토콜 전용 fake가 없음
   - Wave 0에서 `tests/fakes/fake_build_runner.py` 추가 (반환값: `BuildResult`)

3. **`FakeSSIMAdapter` 없음**
   - `ScreenshotDiffAdapter` 전용 fake가 없음
   - Wave 0에서 `tests/fakes/fake_screenshot_diff.py` 추가 (configurable score)

4. **`ServiceContainer`에 phase4 서비스 필드 추가 방식**
   - 현재 `runtime_validator`, `failure_classifier`, `auto_fix_planner`, `rollback_controller` 필드 없음
   - additive-only: `Optional` 필드로 추가 (`None = None`)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Core runtime | ✓ | 3.14 (venv) | — |
| langgraph | Graph loop | ✓ | 1.1.3 | — |
| node / npm / npx / tsc | R-02 eslint fix, VALID-01 build | ✓ | node available | — |
| scikit-image | SSIM (VALID-03) | ✗ | — | **추가 필요: `uv add scikit-image`** |
| Pillow | 이미지 로딩 | ✗ | — | **추가 필요: `uv add Pillow`** |
| playwright | 브라우저 캡처 (VALID-02) | ✗ | — | **추가 필요: `uv add playwright` + `playwright install chromium`** |
| pytest-playwright | playwright 마커 | ✗ | — | **추가 필요: `uv add --dev pytest-playwright`** |
| gitpython | GitAdapter 읽기 | ✓ | ≥3.1.40 | — |
| git (CLI) | worktree, checkpoint | ✓ | 시스템 git | — |

**Missing dependencies with no fallback:**
- `scikit-image` + `Pillow` — VALID-03 구현 불가
- `playwright` — VALID-02 통합 테스트 불가 (단위 테스트는 FakePlaywrightAdapter로 가능)

**Missing dependencies with fallback (unit tests):**
- playwright 없어도 FakePlaywrightAdapter로 단위 테스트 전체 통과 가능
- `pytest.mark.playwright` 마커로 통합 테스트만 CI에서 skip

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest ≥8.0 + pytest-asyncio ≥0.23 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (asyncio_mode=auto) |
| Quick run command | `uv run pytest tests/unit/phase4/ -x` |
| Full suite command | `uv run pytest tests/ -x --ignore=tests/integration` |
| Integration (playwright) | `uv run pytest tests/integration/ -m playwright` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VALID-01 | TempDirSandbox + FakeBuildRunner → RuntimeValidationReport | unit | `uv run pytest tests/unit/phase4/test_runtime_validator.py -x` | ❌ Wave 0 |
| VALID-02 | FakePlaywrightAdapter console/request errors → FailureRecord | unit | `uv run pytest tests/unit/phase4/test_runtime_validator.py::test_playwright_errors -x` | ❌ Wave 0 |
| VALID-02 | 실제 Playwright dev server 캡처 | integration (playwright) | `uv run pytest tests/integration/ -m playwright` | ❌ Wave 5 |
| VALID-03 | FakeSSIMAdapter score < threshold → VisualRegressionReport.pass_result=False | unit | `uv run pytest tests/unit/phase4/test_runtime_validator.py::test_ssim_fail -x` | ❌ Wave 0 |
| VALID-04 | 9개 규칙 각 패치 적용, budget 차감, oscillation 탈출 | unit | `uv run pytest tests/unit/phase4/test_auto_fix_planner.py -x` | ❌ Wave 0 |
| VALID-05 | raw_message → taxonomy_id 매핑 정확도 | unit | `uv run pytest tests/unit/phase4/test_failure_classifier.py -x` | ❌ Wave 0 |
| VALID-07 | FakeRollbackController checkpoint 생성/롤백 | unit | `uv run pytest tests/unit/phase4/test_rollback_controller.py -x` | ❌ Wave 0 |
| Graph loop | validate→router→autofix 백엣지 3회 후 exhausted | unit (graph) | `uv run pytest tests/unit/phase4/test_router.py -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/phase4/ -x`
- **Per wave merge:** `uv run pytest tests/ -x --ignore=tests/integration`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/phase4/__init__.py`
- [ ] `tests/unit/phase4/test_failure_classifier.py`
- [ ] `tests/unit/phase4/test_runtime_validator.py`
- [ ] `tests/unit/phase4/test_auto_fix_planner.py`
- [ ] `tests/unit/phase4/test_rollback_controller.py`
- [ ] `tests/unit/phase4/test_validate_node.py`
- [ ] `tests/unit/phase4/test_autofix_node.py`
- [ ] `tests/unit/phase4/test_router.py`
- [ ] `tests/fakes/fake_build_runner.py` — `BuildResult(success=True/False, stdout, stderr)`
- [ ] `tests/fakes/fake_screenshot_diff.py` — configurable `SSIMResult(score=...)`
- [ ] pytest.mark.playwright 마커 pyproject.toml 등록

---

## Sources

### Primary (HIGH confidence)
- `langgraph==1.1.3` 설치 소스 — `add_conditional_edges` 시그니처, back-edge 루프, `GraphRecursionError` 직접 실행 확인
- `/Users/bjchoi/.../src/ddk/adapters/playwright_browser.py` — PlaywrightAdapter 프로토콜 현재 상태
- `/Users/bjchoi/.../src/ddk/models/validation.py` — FAILURE_TAXONOMY 20개 코드
- `/Users/bjchoi/.../src/ddk/graph/state.py` — GraphState 현재 필드
- `/Users/bjchoi/.../pyproject.toml` — 현재 의존성 (playwright/scikit-image/Pillow 없음 확인)

### Secondary (MEDIUM confidence)
- scikit-image `structural_similarity` API: `channel_axis` 파라미터 확인 (0.19 릴리즈 노트 기반)
- Playwright Python async API `page.on("requestfailed")` 패턴 (playwright-python 공식 문서 패턴)

### Tertiary (LOW confidence)
- `request.failure` property → `str | None` 타입 (playwright-python ≥1.20, 버전 정확도 ±2 마이너)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — langgraph 1.1.3 직접 실행, 미설치 패키지 uv pip show로 확인
- Architecture: HIGH — 기존 코드베이스 전체 분석, thin adapter 패턴, node_wrapper 확인
- Pitfalls: HIGH — UUID oscillation 버그는 CONTEXT.md 원문 분석으로 발견
- Auto-fix regex: MEDIUM — 패턴 설계는 합리적이나 실제 TypeScript/eslint 오류 메시지 포맷은 프로젝트별 가변적

**Research date:** 2025-07-14
**Valid until:** 2025-08-13 (langgraph stable, 30일)

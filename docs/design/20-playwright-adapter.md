# Playwright 어댑터 구현 계약

> `adapters/playwright_browser.py` 완전 명세.
> app boot 감지, 스크린샷 캡처, 콘솔 에러 수집, SSIM 비교.

---

## 1. PlaywrightBrowserAdapter 클래스

```python
# src/ddk/adapters/playwright_browser.py

import asyncio
import base64
import socket
import time
from pathlib import Path
from typing import NamedTuple

from playwright.async_api import async_playwright, Browser, Page, ConsoleMessage


class BootResult(NamedTuple):
    success: bool
    url: str
    duration_seconds: float
    error: str | None = None


class CaptureResult(NamedTuple):
    screenshot_path: Path
    console_errors: list[dict]   # {"type": "error", "text": "...", "location": "..."}
    page_title: str


class PlaywrightBrowserAdapter:
    """
    Playwright 기반 스크린샷 + 콘솔 에러 수집 어댑터.

    사용법:
        adapter = PlaywrightBrowserAdapter(viewport=(1280, 800))
        async with adapter.session(browser_type="chromium") as session:
            boot = await session.wait_for_boot("http://localhost:3001", timeout=30)
            capture = await session.capture(save_path=Path("screenshots/generated.png"))
    """

    def __init__(
        self,
        viewport: tuple[int, int] = (1280, 800),
        browser_type: str = "chromium",
    ):
        self.viewport = viewport
        self.browser_type = browser_type

    async def capture_and_collect(
        self,
        url: str,
        save_path: Path,
        boot_timeout: int = 30,
        capture_timeout: int = 20,
    ) -> tuple[BootResult, CaptureResult | None]:
        """
        단일 진입점: boot 대기 → 캡처 → 결과 반환.
        """
        async with async_playwright() as pw:
            browser = await self._launch_browser(pw)
            try:
                boot = await self._wait_for_boot(url, boot_timeout)
                if not boot.success:
                    return boot, None

                capture = await self._capture_page(
                    browser, url, save_path, capture_timeout
                )
                return boot, capture
            finally:
                await browser.close()

    async def _launch_browser(self, pw) -> Browser:
        launcher = getattr(pw, self.browser_type)
        return await launcher.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )

    async def _wait_for_boot(self, url: str, timeout: int) -> BootResult:
        """
        앱 준비 감지 전략 (3단계 순서 적용):

        1단계: TCP 포트 listen 확인 (빠름, 0.5초 간격)
        2단계: HTTP 200 응답 확인 (앱이 실제로 응답하는지)
        3단계: Playwright navigation 성공 확인 (최종 검증)

        이 순서로 확인하지 않으면:
        - 포트만 열려도 앱이 HTML 응답 못하는 경우 오탐
        - HTTP 200이지만 React 렌더 에러인 경우 → 3단계에서 감지
        """
        from urllib.parse import urlparse
        import aiohttp

        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 3000
        start = time.monotonic()
        deadline = start + timeout

        # 1단계: 포트 열릴 때까지 대기
        while time.monotonic() < deadline:
            if _is_port_open(host, port):
                break
            await asyncio.sleep(0.5)
        else:
            return BootResult(
                success=False,
                url=url,
                duration_seconds=time.monotonic() - start,
                error=f"RUNTIME-004: Port {port} not open after {timeout}s",
            )

        # 2단계: HTTP 200 확인
        http_ok = False
        async with aiohttp.ClientSession() as session:
            for _ in range(10):
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as resp:
                        if resp.status < 500:
                            http_ok = True
                            break
                except Exception:
                    pass
                await asyncio.sleep(1)

        if not http_ok:
            return BootResult(
                success=False,
                url=url,
                duration_seconds=time.monotonic() - start,
                error=f"RUNTIME-004: HTTP not responding at {url}",
            )

        return BootResult(
            success=True,
            url=url,
            duration_seconds=time.monotonic() - start,
        )

    async def _capture_page(
        self,
        browser: Browser,
        url: str,
        save_path: Path,
        timeout: int,
    ) -> CaptureResult:
        """
        페이지 열기 → 콘솔 에러 수집 → 스크린샷 저장.
        """
        console_errors: list[dict] = []
        context = await browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
        )
        page = await context.new_page()

        # 콘솔 에러 수집
        def on_console(msg: ConsoleMessage):
            if msg.type in ("error", "warning"):
                console_errors.append({
                    "type": msg.type,
                    "text": msg.text,
                    "location": f"{msg.location.get('url','')}:{msg.location.get('lineNumber','')}",
                })

        page.on("console", on_console)

        # 페이지 이동 + 렌더링 완료 대기
        await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

        # React 렌더링 완료 대기 (body 내 content 있을 때)
        try:
            await page.wait_for_selector("body > *:not(script):not(style)", timeout=5000)
        except Exception:
            pass  # 타임아웃이어도 스크린샷은 찍음

        save_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(save_path), full_page=False)
        title = await page.title()
        await context.close()

        return CaptureResult(
            screenshot_path=save_path,
            console_errors=console_errors,
            page_title=title,
        )


def _is_port_open(host: str, port: int) -> bool:
    """TCP 포트 열림 확인 (non-async)."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except (OSError, ConnectionRefusedError):
        return False
```

---

## 2. SSIM 계산 어댑터

```python
# src/ddk/adapters/screenshot_diff.py

import numpy as np
from pathlib import Path
from skimage import io, color
from skimage.metrics import structural_similarity as ssim
from skimage.transform import resize
from ddk.models.visual import MismatchRegion


class SSIMDiffResult:
    ssim: float
    changed_pixel_ratio: float
    diff_image_path: Path | None
    mismatch_regions: list[MismatchRegion]


def compute_ssim_diff(
    reference_path: Path,
    generated_path: Path,
    diff_output_path: Path | None = None,
    critical_regions: list[tuple[float, float, float, float]] | None = None,
) -> SSIMDiffResult:
    """
    두 스크린샷의 SSIM + pixel diff 계산.
    이미지 크기가 다르면 generated를 reference 크기로 리사이즈.
    critical_regions는 normalized box(x, y, width, height) 목록.
    """
    ref_img = io.imread(str(reference_path))
    gen_img = io.imread(str(generated_path))

    # RGBA → RGB 변환
    if ref_img.shape[-1] == 4:
        ref_img = ref_img[..., :3]
    if gen_img.shape[-1] == 4:
        gen_img = gen_img[..., :3]

    # 크기 맞춤 (reference 기준)
    if ref_img.shape != gen_img.shape:
        gen_img = (
            resize(gen_img, ref_img.shape, anti_aliasing=True) * 255
        ).astype(np.uint8)

    # Grayscale 변환 후 SSIM
    ref_gray = color.rgb2gray(ref_img)
    gen_gray = color.rgb2gray(gen_img)

    score, diff_map = ssim(
        ref_gray, gen_gray,
        data_range=ref_gray.max() - ref_gray.min(),
        full=True,
    )

    # Pixel diff
    diff_abs = np.abs(ref_gray.astype(float) - gen_gray.astype(float))
    changed_ratio = float(np.mean(diff_abs > 0.05))  # 5% 임계치

    # Diff 이미지 저장
    if diff_output_path:
        diff_vis = ((1 - diff_map) * 255).astype(np.uint8)
        io.imsave(str(diff_output_path), diff_vis)

    result = SSIMDiffResult()
    result.ssim = float(score)
    result.changed_pixel_ratio = changed_ratio
    result.diff_image_path = diff_output_path
    result.mismatch_regions = _find_mismatch_regions(
        diff_map,
        threshold=0.7,
        critical_regions=critical_regions or [],
    )

    return result


def _find_mismatch_regions(
    diff_map: np.ndarray,
    threshold: float = 0.7,
    critical_regions: list[tuple[float, float, float, float]] | None = None,
) -> list[MismatchRegion]:
    """
    diff_map의 SSIM < threshold 영역을 MismatchRegion으로 변환.
    P0 구현은 deterministic 2단계 알고리즘을 사용한다:

    1. 전체 이미지를 3x3 grid로 분할해 각 셀 평균 SSIM 계산
    2. 각 셀이 critical region과 겹치면 severity를 한 단계 상향

    즉 "mismatch region detection"은 library 마법이 아니라
    grid scan + critical overlay 규칙으로 고정한다.
    """
    h, w = diff_map.shape
    regions = []
    grid_rows, grid_cols = 3, 3
    critical_regions = critical_regions or []

    for row in range(grid_rows):
        for col in range(grid_cols):
            r0 = row * h // grid_rows
            r1 = (row + 1) * h // grid_rows
            c0 = col * w // grid_cols
            c1 = (col + 1) * w // grid_cols

            cell_ssim = float(np.mean(diff_map[r0:r1, c0:c1]))
            if cell_ssim < threshold:
                overlaps_critical = _intersects_critical_region(
                    (c0 / w, r0 / h, (c1 - c0) / w, (r1 - r0) / h),
                    critical_regions,
                )
                regions.append(MismatchRegion(
                    x=c0 / w,
                    y=r0 / h,
                    width=(c1 - c0) / w,
                    height=(r1 - r0) / h,
                    severity=(
                        "critical"
                        if overlaps_critical or cell_ssim < 0.5
                        else "major"
                    ),
                ))

    return regions


def _intersects_critical_region(
    cell: tuple[float, float, float, float],
    critical_regions: list[tuple[float, float, float, float]],
) -> bool:
    cx, cy, cw, ch = cell
    for rx, ry, rw, rh in critical_regions:
        if not (cx + cw <= rx or rx + rw <= cx or cy + ch <= ry or ry + rh <= cy):
            return True
    return False
```

---

## 3. Vite dev server 시작 + 포트 할당

```python
# src/ddk/adapters/sandbox/dev_server.py

import asyncio
import socket
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass
class DevServerSession:
    url: str
    port: int
    process: asyncio.subprocess.Process


def _find_free_port(start: int = 3001) -> int:
    """3001~3100 범위에서 비어 있는 포트를 찾는다."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    raise RuntimeError("사용 가능한 포트가 없습니다 (3001~3100)")


@asynccontextmanager
async def vite_dev_server(
    worktree_path,
    timeout: int = 30,
):
    """
    Vite dev server를 ephemeral 포트에서 실행.

    사용법:
        async with vite_dev_server(sandbox.worktree_path) as session:
            boot = await adapter.wait_for_boot(session.url, timeout=30)
    """
    port = _find_free_port()
    proc = await asyncio.create_subprocess_exec(
        "pnpm", "dev", f"--port={port}", "--host=localhost",
        cwd=str(worktree_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    session = DevServerSession(
        url=f"http://localhost:{port}",
        port=port,
        process=proc,
    )

    try:
        yield session
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
```

---

## 4. RuntimeValidationAggregator 구현 계약

```python
# src/ddk/services/runtime_validator.py

from ddk.models.validation import RuntimeValidationReport, FailureRecord, FAILURE_TAXONOMY
from ddk.adapters.sandbox.worktree import WorktreeSandbox
from ddk.adapters.sandbox.dev_server import vite_dev_server
from ddk.adapters.playwright_browser import PlaywrightBrowserAdapter


class RuntimeValidationAggregator:

    async def validate(
        self,
        artifacts,
        repo_path,
        case_id: str,
        pre_run_ref: str | None = None,
        skip_visual_boot: bool = False,
    ) -> RuntimeValidationReport:
        """
        8단계 순서:
        1. sandbox 생성 + 체크포인트
        2. 파일 적용
        3. pnpm install
        4. pnpm build → BUILD gate
        5. pnpm tsc --noEmit → TYPE gate
        6. pnpm eslint src → LINT gate
        7. pnpm dev 시작 + boot 대기 → RUNTIME gate
        8. Playwright 콘솔 에러 수집
        """
        all_failures: list[FailureRecord] = []
        sandbox_id = f"validate-{case_id}"

        async with WorktreeSandbox.create(repo_path, sandbox_id) as sandbox:
            # 체크포인트 (auto-fix 시 롤백용)
            checkpoint = sandbox.create_checkpoint(f"pre-validate-{case_id}")

            await sandbox.apply_files(artifacts.files)

            # install
            install = await sandbox.run_command(
                ["pnpm", "install", "--frozen-lockfile"], timeout=60
            )

            # BUILD
            build = await sandbox.run_command(["pnpm", "build"], timeout=90)
            build_status = "pass" if build.success else "fail"
            if not build.success:
                all_failures.extend(_parse_build_errors(build.stderr))

            # TYPE
            typecheck = await sandbox.run_command(
                ["pnpm", "exec", "tsc", "--noEmit"], timeout=60
            )
            type_status = "pass" if typecheck.success else "fail"
            if not typecheck.success:
                all_failures.extend(_parse_type_errors(typecheck.stdout))

            # LINT
            lint = await sandbox.run_command(
                ["pnpm", "exec", "eslint", "src", "--format=json"], timeout=30
            )
            lint_status = "pass" if lint.success else "fail"
            if not lint.success:
                all_failures.extend(_parse_lint_errors(lint.stdout))

            # RUNTIME boot (visual boot 포함)
            runtime_status = "skip"
            console_errors = []

            if build.success and not skip_visual_boot:
                async with vite_dev_server(sandbox.worktree_path) as dev:
                    adapter = PlaywrightBrowserAdapter()
                    boot, capture = await adapter.capture_and_collect(
                        url=dev.url,
                        save_path=repo_path / ".ddk" / "cases" / case_id / "screenshots" / "generated.png",
                        boot_timeout=30,
                        capture_timeout=20,
                    )
                    if boot.success and capture:
                        runtime_status = "pass"
                        console_errors = [
                            record
                            for record in (
                                _classify_console_error(e)
                                for e in capture.console_errors
                                if e["type"] == "error"
                            )
                            if record is not None
                        ]
                        all_failures.extend(console_errors)
                    else:
                        runtime_status = "fail"
                        all_failures.append(FailureRecord(
                            taxonomy_id="RUNTIME-004",
                            severity="critical",
                            message=boot.error or "App boot failed",
                        ))

        overall = "fail" if any(
            f.severity in ("critical", "error") for f in all_failures
        ) else "pass"

        return RuntimeValidationReport(
            case_id=case_id,
            sandbox_id=sandbox_id,
            build_status=build_status,
            type_status=type_status,
            lint_status=lint_status,
            runtime_status=runtime_status,
            console_errors=console_errors,
            all_failures=all_failures,
            overall_status=overall,
        )


def _parse_build_errors(stderr: str) -> list[FailureRecord]:
    """Vite build 에러 파싱 → FailureRecord 목록."""
    records = []
    for line in stderr.splitlines():
        if "error TS" in line:
            records.append(FailureRecord(
                taxonomy_id="BUILD-001",
                severity="error",
                message=line.strip(),
            ))
        elif "Cannot find module" in line or "Module not found" in line:
            records.append(FailureRecord(
                taxonomy_id="BUILD-002",
                severity="error",
                message=line.strip(),
            ))
    return records


def _parse_type_errors(stdout: str) -> list[FailureRecord]:
    """tsc --noEmit 출력 파싱."""
    records = []
    for line in stdout.splitlines():
        if ": error TS" in line:
            parts = line.split("(")
            file_path = parts[0].strip() if parts else None
            records.append(FailureRecord(
                taxonomy_id="TYPE-001",
                severity="error",
                message=line.strip(),
                file_path=file_path,
            ))
    return records


def _parse_lint_errors(stdout: str) -> list[FailureRecord]:
    """ESLint JSON 포맷 파싱."""
    import json
    records = []
    try:
        data = json.loads(stdout)
        for file_result in data:
            for msg in file_result.get("messages", []):
                if msg["severity"] >= 2:
                    records.append(FailureRecord(
                        taxonomy_id="LINT-001",
                        severity="error",
                        message=msg["message"],
                        file_path=file_result["filePath"],
                        line_number=msg.get("line"),
                    ))
    except (json.JSONDecodeError, KeyError):
        pass
    return records


def _classify_console_error(msg: dict) -> FailureRecord | None:
    """
    console error -> FailureRecord 매핑은 regex-first deterministic 규칙을 사용한다.
    LLM 기반 분류는 P0 범위 밖이다.
    """
    import re

    text = msg.get("text", "")
    location = msg.get("location")

    patterns = [
        (r"Cannot read (properties|property) of (undefined|null)", "RUNTIME-001", "error"),
        (r"Failed to fetch|NetworkError|ERR_", "RUNTIME-002", "error"),
        (r"Rendered fewer hooks|Invalid hook call|Minified React error", "RUNTIME-003", "critical"),
    ]

    for pattern, taxonomy_id, severity in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return FailureRecord(
                taxonomy_id=taxonomy_id,
                severity=severity,
                message=text,
                file_path=location,
            )

    if text:
        return FailureRecord(
            taxonomy_id="RUNTIME-003",
            severity="error",
            message=text,
            file_path=location,
        )

    return None
```

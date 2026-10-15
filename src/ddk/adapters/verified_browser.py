"""Execute immutable browser criteria; execution authorization belongs to the caller."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import ipaddress
import os
import stat
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit

from PIL import Image, ImageChops, ImageStat
from playwright.async_api import (
    Browser,
    BrowserContext,
    ConsoleMessage,
    Frame,
    Locator,
    Page,
    Request,
    Route,
    WebSocketRoute,
    async_playwright,
    expect,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ddk.adapters.screenshot_diff_local import flatten_to_rgb
from ddk.models.verified_change import (
    Record,
    canonical_json,
    contract_validator,
    parse_record,
    record_digest,
    relative_url,
    validate_record,
)
from ddk.security.redact import redact_string

_MAX_IMAGE_PIXELS = 16_777_216
_MAX_OBSERVATION_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class BrowserSettings:
    environment: Record
    environment_sha256: str
    frozen_time: str
    executable_path: str | None = None
    cleanup_timeout_ms: int = 10_000
    max_artifact_bytes: int = 200 * 1024 * 1024


@dataclass(frozen=True)
class VisualReference:
    data: bytes
    sha256: str
    width: int
    height: int
    viewport: tuple[int, int]
    environment_sha256: str
    mask_sha256: str | None = None


@dataclass(frozen=True)
class RGBComparison:
    passed: bool
    mismatch_ppm: int
    ssim: float
    diff_png: bytes


@dataclass(frozen=True)
class BrowserRun:
    result: Record
    artifacts: list[Record]
    cleanup_complete: bool


def compare_rgb(
    reference: bytes, actual: bytes, *, rgb_tolerance: int, max_mismatch_ppm: int
) -> RGBComparison:
    """Compare approved RGB components without resizing, masking or updating a reference."""
    if not 0 <= rgb_tolerance <= 255 or not 0 <= max_mismatch_ppm <= 1_000_000:
        raise ValueError("invalid_rgb_threshold")
    with Image.open(io.BytesIO(reference)) as source, Image.open(io.BytesIO(actual)) as candidate:
        if source.size != candidate.size:
            raise ValueError("image_size_mismatch")
        if source.width * source.height > _MAX_IMAGE_PIXELS:
            raise ValueError("image_size_limit")
        expected, observed = flatten_to_rgb(source), flatten_to_rgb(candidate)
    difference = ImageChops.difference(expected, observed)
    red, green, blue = difference.split()
    component = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = sum(component.histogram()[rgb_tolerance + 1 :])
    pixels = expected.width * expected.height
    mismatch_ppm = (changed * 1_000_000 + pixels - 1) // pixels
    buffer = io.BytesIO()
    difference.save(buffer, format="PNG")
    return RGBComparison(
        passed=changed * 1_000_000 <= max_mismatch_ppm * pixels,
        mismatch_ppm=mismatch_ppm,
        ssim=_ssim(expected, observed),
        diff_png=buffer.getvalue(),
    )


def _ssim(reference: Image.Image, actual: Image.Image) -> float:
    left, right = reference.convert("L"), actual.convert("L")
    a, b = ImageStat.Stat(left), ImageStat.Stat(right)
    difference = ImageStat.Stat(ImageChops.difference(left, right))
    mean_a, mean_b = a.mean[0], b.mean[0]
    second_moment_difference = difference.var[0] + difference.mean[0] ** 2
    cross = (a.var[0] + mean_a**2 + b.var[0] + mean_b**2 - second_moment_difference) / 2
    covariance = cross - mean_a * mean_b
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    score = ((2 * mean_a * mean_b + c1) * (2 * covariance + c2)) / (
        (mean_a**2 + mean_b**2 + c1) * (a.var[0] + b.var[0] + c2)
    )
    return max(0.0, min(1.0, score))


def validate_fragment(record: Record, name: str) -> None:
    validator = cast(Any, contract_validator())
    schema: Record = {"$defs": validator.schema["$defs"], "$ref": "#/$defs/" + name}
    errors = list(validator.evolve(schema=schema).iter_errors(record))
    if errors:
        raise ValueError("invalid_" + name.lower())


def _origin(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("nonlocal_origin")
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = parsed.hostname == "localhost"
    if not local or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("nonlocal_origin")
    _ = parsed.port
    return parsed._replace(path="", query="", fragment="").geturl()


def _same_origin(url: str, origin: str) -> bool:
    value, owned = urlsplit(url), urlsplit(origin)
    return (
        value.scheme == owned.scheme
        and value.hostname == owned.hostname
        and (value.port or (443 if value.scheme == "https" else 80))
        == (owned.port or (443 if owned.scheme == "https" else 80))
        and value.username is None
        and value.password is None
    )


def _approved_url(path: str, origin: str) -> str:
    if not relative_url(path):
        raise ValueError("external_or_invalid_url")
    result = urljoin(origin + "/", path)
    if not _same_origin(result, origin):
        raise ValueError("external_or_invalid_url")
    return result


def _locator(page: Page, selector: Record) -> Locator:
    strategy, value = selector["strategy"], selector["value"]
    if strategy == "role":
        return page.get_by_role(value, name=selector["name"], exact=True)
    if strategy == "label":
        return page.get_by_label(value, exact=True)
    if strategy == "test-id":
        return page.get_by_test_id(value)
    if strategy == "css" and not any(
        token in value for token in [">>", "xpath=", "text=", "role="]
    ):
        return page.locator("css=" + value)
    raise ValueError("unsupported_selector")


def _file_digest(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare(
    flow: bytes,
    check: Record,
    base_url: str,
    fixture_sha256: str,
    settings: BrowserSettings,
    references: Mapping[str, VisualReference],
) -> tuple[Record, str]:
    validate_fragment(check, "Check")
    if hashlib.sha256(flow).hexdigest() != check["definition_sha256"]:
        raise ValueError("criteria_hash_mismatch")
    definition = parse_record(flow)
    validate_record(settings.environment)
    if record_digest(settings.environment) != settings.environment_sha256:
        raise ValueError("environment_mismatch")
    if definition["check_id"] != check["check_id"] or check["kind"] not in {"browser", "visual"}:
        raise ValueError("check_flow_mismatch")
    if check["command_argv"] or check["viewport"] is None:
        raise ValueError("invalid_browser_check")
    if check["kind"] == "visual" and not any(
        step["action"] == "snapshot" for step in definition["steps"]
    ):
        raise ValueError("visual_steps_missing")
    if not (
        definition["fixture_sha256"] == fixture_sha256 == settings.environment["fixture_sha256"]
    ):
        raise ValueError("fixture_mismatch")
    frozen = datetime.fromisoformat(settings.frozen_time)
    if frozen.tzinfo is None:
        raise ValueError("fixed_time_timezone_missing")
    if not 1 <= settings.cleanup_timeout_ms <= 10_000 or settings.max_artifact_bytes < 1:
        raise ValueError("invalid_browser_limits")
    origin = _origin(base_url)
    _approved_url(definition["entry_path"], origin)
    viewport = (check["viewport"]["width"], check["viewport"]["height"])
    for step in definition["steps"]:
        if step["action"] in {"goto", "expect-url"}:
            _approved_url(step["value"], origin)
        selector = step["selector"]
        if selector and selector["strategy"] != "role" and selector["name"] is not None:
            raise ValueError("unused_selector_name")
        if (
            selector
            and selector["strategy"] == "css"
            and any(token in selector["value"] for token in [">>", "xpath=", "text=", "role="])
        ):
            raise ValueError("unsupported_selector")
        if step["action"] == "snapshot":
            reference = references.get(step["reference_path"])
            if reference is None:
                raise ValueError("reference_missing")
            if reference.mask_sha256 is not None:
                raise ValueError("mask_unsupported")
            if (
                reference.viewport != viewport
                or reference.environment_sha256 != settings.environment_sha256
            ):
                raise ValueError("reference_environment_mismatch")
            if hashlib.sha256(reference.data).hexdigest() != reference.sha256:
                raise ValueError("reference_hash_mismatch")
            with Image.open(io.BytesIO(reference.data)) as image:
                if image.size != (reference.width, reference.height):
                    raise ValueError("reference_size_mismatch")
    return definition, origin


@dataclass
class _Observation:
    errors: list[Record] = field(default_factory=lambda: list[Record]())
    steps: list[str] = field(default_factory=lambda: list[str]())
    visuals: list[Record] = field(default_factory=lambda: list[Record]())
    pending: set[Request] = field(default_factory=lambda: set[Request]())
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    closing: bool = False
    _size: int = 0

    def record(self, code: str, detail: str = "") -> None:
        if self.closing:
            return
        detail = detail.encode("utf-8", errors="backslashreplace").decode("utf-8")
        item = {"code": code, "detail": detail[:4096]}
        size = len(canonical_json(item))
        if self._size + size > _MAX_OBSERVATION_BYTES:
            if not self.errors or self.errors[-1]["code"] != "observation_limit":
                self.errors.append({"code": "observation_limit", "detail": ""})
            return
        self._size += size
        self.errors.append(item)

    def console(self, message: ConsoleMessage) -> None:
        normalized = message.text.lower().replace(" ", "")
        if message.type == "error":
            self.record("console_error", message.text)
        elif "serviceworker" in normalized and "block" in normalized:
            self.record("serviceworker_blocked", message.text)

    def finished(self, request: Request) -> None:
        self.pending.discard(request)
        self.changed.set()


async def _gate(route: Route, origin: str, page: Page, observation: _Observation) -> None:
    request = route.request
    if request.is_navigation_request():
        try:
            additional_page = request.frame.page is not page
        except Exception:
            additional_page = True
        if additional_page:
            observation.record("popup_blocked", request.url)
            if not _same_origin(request.url, origin):
                observation.record("external_request_blocked", request.url)
            await route.abort("blockedbyclient")
            return
    if not _same_origin(request.url, origin):
        observation.record("external_request_blocked", request.url)
        await route.abort("blockedbyclient")
        return
    try:
        response = await route.fetch(max_redirects=0, max_retries=0)
        try:
            if 300 <= response.status < 400:
                location = response.headers.get("location", "")
                try:
                    valid = bool(location) and not any(
                        character == "\\" or ord(character) < 32 or ord(character) == 127
                        for character in location
                    )
                    target = urljoin(request.url, location)
                    internal = valid and _same_origin(target, origin)
                except ValueError:
                    internal = False
                observation.record(
                    "redirect_unavailable" if internal else "redirect_blocked", request.url
                )
                await route.abort("blockedbyclient")
            else:
                if response.status >= 400:
                    observation.record("http_error", str(response.status))
                await route.fulfill(response=response)
        finally:
            await response.dispose()
    except Exception as error:
        observation.record("request_failed", type(error).__name__)
        with contextlib.suppress(Exception):
            await route.abort("failed")


async def _block_socket(socket: WebSocketRoute, observation: _Observation) -> None:
    observation.record("websocket_blocked", socket.url)
    await socket.close(code=1008, reason="approved HTTP origin only")


def _frame_origin(frame: Frame, origin: str, observation: _Observation) -> None:
    if frame.url != "about:blank" and not _same_origin(frame.url, origin):
        observation.record("navigation_blocked", frame.url)


async def _step(
    step: Record,
    page: Page,
    origin: str,
    references: Mapping[str, VisualReference],
    observation: _Observation,
    publish: Any,
) -> None:
    timeout = step["timeout_ms"]
    action = step["action"]
    selected = _locator(page, step["selector"]) if step["selector"] else None
    if action == "goto":
        await page.goto(_approved_url(step["value"], origin), wait_until="load", timeout=timeout)
    elif action == "expect-url":
        await expect(page).to_have_url(_approved_url(step["value"], origin), timeout=timeout)
    elif action == "expect-ax-tree":
        await expect(selected or page.locator("body")).to_match_aria_snapshot(
            step["value"], timeout=timeout
        )
    elif action == "expect-no-console-error":
        if any(item["code"] in {"console_error", "page_error"} for item in observation.errors):
            raise AssertionError("console_error")
    elif action == "snapshot":
        await _ax(page, publish, step["step_id"])
        reference = references[step["reference_path"]]
        image = await (selected or page).screenshot(
            animations="disabled", caret="hide", timeout=timeout
        )
        comparison = compare_rgb(
            reference.data,
            image,
            rgb_tolerance=step["rgb_tolerance"],
            max_mismatch_ppm=step["max_mismatch_ppm"],
        )
        publish("screenshot", image)
        publish("diff", comparison.diff_png)
        observation.visuals.append(
            {
                "step_id": step["step_id"],
                "mismatch_ppm": comparison.mismatch_ppm,
                "ssim": comparison.ssim,
                "passed": comparison.passed,
            }
        )
        if not comparison.passed:
            observation.record("rgb_mismatch", step["step_id"])
    elif selected is not None:
        if action == "click":
            await selected.click(timeout=timeout)
        elif action == "fill":
            await selected.fill(step["value"], timeout=timeout)
        elif action == "press":
            await selected.press(step["value"], timeout=timeout)
        elif action in {"expect-visible", "expect-ax-role"}:
            await expect(selected).to_be_visible(timeout=timeout)
        elif action == "expect-text":
            await expect(selected).to_have_text(step["value"], timeout=timeout, use_inner_text=True)
        elif action == "expect-count":
            await expect(selected).to_have_count(step["count"], timeout=timeout)
        else:
            raise ValueError("unsupported_action")
    else:
        raise ValueError("selector_missing")
    if not _same_origin(page.url, origin):
        observation.record("navigation_blocked", page.url)
    observation.steps.append(step["step_id"])


async def _ax(page: Page, publish: Any, step_id: str = "final") -> None:
    snapshot = await page.locator("body").aria_snapshot(timeout=500)
    styles = await page.locator("body").evaluate(
        "element => Array.from(element.querySelectorAll('*')).slice(0,100).map(e => {"
        "const s=getComputedStyle(e),r=e.getBoundingClientRect();return {tag:e.tagName,"
        "display:s.display,color:s.color,fontSize:s.fontSize,width:r.width,height:r.height}})"
    )
    publish(
        "ax_snapshot",
        canonical_json(
            {
                "format": "playwright-aria/1",
                "step_id": step_id,
                "snapshot": redact_string(snapshot),
                "styles": styles,
            }
        ),
    )


def _publish(
    output_dir: Path, artifacts: list[Record], kind: str, payload: bytes, limit: int
) -> None:
    if sum(item["size_bytes"] for item in artifacts) + len(payload) > limit:
        raise ValueError("artifact_size_limit")
    if any(path.is_symlink() for path in [output_dir, *output_dir.parents]):
        raise ValueError("unsafe_output_directory")
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    artifact_id = uuid.uuid4().hex
    name = artifact_id + (
        ".ax.json" if kind == "ax_snapshot" else ".json" if kind == "data" else ".png"
    )
    directory = os.open(output_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(
            name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory
        )
        with os.fdopen(descriptor, "wb") as target:
            os.fchmod(target.fileno(), 0o600)
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
            if not stat.S_ISREG(os.fstat(target.fileno()).st_mode):
                raise ValueError("artifact_not_regular")
    finally:
        os.close(directory)
    artifact = {
        "artifact_id": artifact_id,
        "kind": kind,
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
        "sensitive": True,
        "public_export_allowed": False,
    }
    validate_fragment(artifact, "Artifact")
    artifacts.append(artifact)


@dataclass
class _DriverOwner:
    manager: Any

    async def close(self) -> None:
        await self.manager.__aexit__()


async def _cleanup(resources: list[Any], timeout_ms: int) -> tuple[bool, bool]:
    async def close_all() -> bool:
        complete = True
        for resource in reversed(resources):
            try:
                await resource.close()
            except Exception:
                complete = False
        return complete

    interrupted = False
    task = asyncio.create_task(close_all())
    deadline = time.monotonic_ns() + timeout_ms * 1_000_000
    while not task.done():
        remaining = (deadline - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            task.cancel()
            return False, interrupted
        try:
            await asyncio.wait({task}, timeout=remaining)
        except asyncio.CancelledError:
            interrupted = True
    return task.result(), interrupted


async def run_flow(
    flow: bytes,
    *,
    check: Record,
    base_url: str,
    output_dir: Path,
    fixture_sha256: str,
    references: Mapping[str, VisualReference],
    settings: BrowserSettings,
    phase: Literal["baseline", "candidate"] = "candidate",
    round_no: int = 0,
    deadline_ns: int | None = None,
) -> BrowserRun:
    """Observe one approved flow in one fresh context; never grant execution permission."""
    started = time.monotonic_ns()
    observation = _Observation()
    artifacts: list[Record] = []
    resources: list[Any] = []
    pages: list[Page] = []
    status = "unavailable"
    reason: str | None = None
    cancelled: asyncio.CancelledError | None = None
    cleanup_complete = True

    def publish(kind: str, payload: bytes) -> None:
        _publish(output_dir, artifacts, kind, payload, settings.max_artifact_bytes)

    try:
        definition, origin = _prepare(flow, check, base_url, fixture_sha256, settings, references)
        if phase not in {"baseline", "candidate"} or not 0 <= round_no <= 10:
            raise ValueError("invalid_result_scope")
        deadline = min(
            deadline_ns if deadline_ns is not None else 2**63,
            started + check["timeout_ms"] * 1_000_000,
        )
        if time.monotonic_ns() >= deadline:
            raise TimeoutError

        async def execute() -> tuple[Literal["passed", "failed", "unavailable"], str | None]:
            manager = async_playwright()
            resources.append(_DriverOwner(manager))
            playwright = await manager.start()
            binary = settings.executable_path or playwright.chromium.executable_path
            if (
                _file_digest(binary) != settings.environment["browser_binary_sha256"]
                or version("playwright") != settings.environment["playwright_version"]
            ):
                raise ValueError("browser_environment_mismatch")
            browser: Browser = await playwright.chromium.launch(
                headless=True,
                chromium_sandbox=True,
                executable_path=binary,
                args=["--hide-scrollbars", "--mute-audio", "--force-color-profile=srgb"],
                timeout=max(1, (deadline - time.monotonic_ns()) / 1_000_000),
            )
            resources.append(browser)
            if browser.version != settings.environment["browser_version"]:
                raise ValueError("browser_environment_mismatch")
            context: BrowserContext = await browser.new_context(
                viewport=check["viewport"],
                locale=settings.environment["locale"],
                timezone_id=settings.environment["timezone"],
                reduced_motion="reduce",
                color_scheme="light",
                device_scale_factor=1,
                accept_downloads=False,
                service_workers="block",
            )
            resources.append(context)
            page = await context.new_page()
            pages.append(page)
            page.on("console", observation.console)
            page.on("pageerror", lambda error: observation.record("page_error", str(error)))
            page.on("request", lambda request: observation.pending.add(request))
            page.on("requestfinished", observation.finished)

            def failed(request: Request) -> None:
                observation.record("request_failed", request.failure or "unknown")
                observation.finished(request)

            page.on("requestfailed", failed)
            page.on("framenavigated", lambda frame: _frame_origin(frame, origin, observation))

            async def close_popup(additional: Page) -> None:
                observation.record("popup_blocked")
                await additional.close()

            context.on("page", close_popup)
            context.on("serviceworker", lambda _: observation.record("serviceworker_blocked"))
            page.on("download", lambda _: observation.record("download_blocked"))
            await context.route("**/*", lambda route: _gate(route, origin, page, observation))
            await context.route_web_socket("**", lambda socket: _block_socket(socket, observation))
            await page.clock.set_fixed_time(datetime.fromisoformat(settings.frozen_time))
            await page.goto(_approved_url(definition["entry_path"], origin), wait_until="load")
            for approved_step in definition["steps"]:
                step_deadline = min(
                    deadline, time.monotonic_ns() + approved_step["timeout_ms"] * 1_000_000
                )
                async with asyncio.timeout(max(0, (step_deadline - time.monotonic_ns()) / 1e9)):
                    try:
                        await asyncio.create_task(
                            _step(approved_step, page, origin, references, observation, publish)
                        )
                    except PlaywrightTimeoutError as error:
                        raise TimeoutError(str(error)) from error
                if time.monotonic_ns() >= step_deadline:
                    raise TimeoutError
            while observation.pending:
                observation.changed.clear()
                await observation.changed.wait()
            if not artifacts:
                publish("screenshot", await page.screenshot(animations="disabled", caret="hide"))
            status: Literal["passed", "failed", "unavailable"] = (
                "unavailable"
                if any(item["code"] == "redirect_unavailable" for item in observation.errors)
                else "failed"
                if observation.errors
                else "passed"
            )
            reason = observation.errors[0]["code"] if observation.errors else None
            return status, reason

        async with asyncio.timeout(max(0, (deadline - time.monotonic_ns()) / 1e9)):
            status, reason = await asyncio.create_task(execute())
    except asyncio.CancelledError as error:
        cancelled = error
        reason = "cancelled"
    except (TimeoutError, AssertionError) as error:
        status, reason = (
            "failed",
            "expectation_failed" if isinstance(error, AssertionError) else "timeout",
        )
        observation.record(reason)
    except Exception as error:
        if observation.errors:
            reason = observation.errors[0]["code"]
            status = "unavailable" if reason == "redirect_unavailable" else "failed"
        else:
            reason = str(error) if isinstance(error, ValueError) else "browser_unavailable"
            reason = reason[:128] or "browser_unavailable"
        observation.record(reason or "browser_unavailable", f"{type(error).__name__}: {error}")
    finally:
        if pages and not pages[-1].is_closed():
            try:
                async with asyncio.timeout(min(1, settings.cleanup_timeout_ms / 1000)):
                    await _ax(pages[-1], publish)
            except Exception:
                status, reason = "unavailable", "ax_snapshot_unavailable"
        observation.closing = True
        cleanup_complete, interrupted = await _cleanup(
            resources, min(10_000, max(1, settings.cleanup_timeout_ms))
        )
        if interrupted and cancelled is None:
            cancelled = asyncio.CancelledError()
            reason = "cancelled"
        if not cleanup_complete:
            status, reason = "unavailable", "cleanup_failed"
        try:
            publish(
                "data",
                canonical_json(
                    {
                        "steps": observation.steps,
                        "errors": observation.errors,
                        "visuals": observation.visuals,
                        "environment_sha256": settings.environment_sha256,
                        "fixture_sha256": fixture_sha256,
                        "cleanup_complete": cleanup_complete,
                        "reason_code": reason,
                    }
                ),
            )
        except Exception:
            status, reason = "unavailable", "artifact_unavailable"
    if cancelled is not None:
        if not cleanup_complete:
            cancelled.add_note("browser_cleanup_incomplete")
        raise cancelled
    result: Record = {
        "check_id": check.get("check_id", "invalid"),
        "phase": phase,
        "status": status,
        "exit_code": None,
        "executed_count": len(observation.steps),
        "failed_count": 0 if status == "passed" else 1,
        "skipped_count": 0,
        "retry_count": 0,
        "duration_ms": (time.monotonic_ns() - started) // 1_000_000,
        "reason_code": reason,
        "artifact_ids": [a["artifact_id"] for a in artifacts],
        "evidence_origin": "trusted-observer",
        "round_no": round_no,
    }
    validate_fragment(result, "CheckResult")
    return BrowserRun(result, artifacts, cleanup_complete)


BrowserObservation = _Observation
gate_request = _gate
block_socket = _block_socket

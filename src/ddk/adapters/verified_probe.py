"""One headless observation with private artifacts and explicit cleanup evidence."""

from __future__ import annotations

import asyncio
import copy
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import async_playwright

from ddk.adapters.verified_browser import (
    BrowserObservation,
    block_socket,
    compare_rgb,
    gate_request,
)
from ddk.models.verified_change import Record, canonical_json, decode_json, record_digest, safe_path
from ddk.security.file_access import read_regular
from ddk.security.redact import redact_string
from ddk.services.durable_files import atomic_write, ensure_directory
from ddk.services.source_snapshot import SnapshotFile, manifest_digest
from ddk.services.verified_change_engine import record_time
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_host import observe_environment


async def capture_probe(
    url: str,
    output: Path,
    *,
    viewport: tuple[int, int] = (1280, 800),
    selector: str | None = None,
    repository: Path | None = None,
    reference: Path | None = None,
    timeout_ms: int = 15000,
    frozen_time: str = "2026-01-01T00:00:00+00:00",
) -> Record:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("invalid_probe_url")
    if (
        any(type(v) is not int or not 1 <= v <= 16384 for v in viewport)
        or viewport[0] * viewport[1] > 16_777_216
    ):
        raise ValueError("invalid_viewport")
    if not 1 <= timeout_ms <= 60000:
        raise ValueError("invalid_probe_timeout")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    environment, binary = await observe_environment(repository or Path.cwd())
    observation = BrowserObservation()
    artifacts: list[Record] = []
    cleanup = False
    bounding = None
    reason = None

    def save(name: str, kind: str, payload: bytes) -> None:
        if (
            len(payload) > 20 * 1024**2
            or sum(a["size_bytes"] for a in artifacts) + len(payload) > 40 * 1024**2
        ):
            raise ValueError("probe_artifact_limit")
        ensure_directory(output)
        atomic_write(output / name, payload)
        artifacts.append(
            {
                "path": name,
                "kind": kind,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
                "sensitive": True,
                "public_export_allowed": False,
            }
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            chromium_sandbox=True,
            executable_path=binary,
            args=["--hide-scrollbars", "--mute-audio", "--force-color-profile=srgb"],
        )
        context = None
        try:
            async with asyncio.timeout(timeout_ms / 1000):
                context = await browser.new_context(
                    viewport={"width": viewport[0], "height": viewport[1]},
                    locale="en-US",
                    timezone_id="UTC",
                    reduced_motion="reduce",
                    color_scheme="light",
                    device_scale_factor=1,
                    accept_downloads=False,
                    service_workers="block",
                )
                page = await context.new_page()
                page.on("console", observation.console)
                page.on("pageerror", lambda error: observation.record("page_error", str(error)))
                page.on(
                    "requestfailed",
                    lambda request: observation.record(
                        "request_failed", request.failure or "unknown"
                    ),
                )
                context.on("page", lambda additional: additional.close())
                page.on("download", lambda _: observation.record("download_blocked"))
                await context.route(
                    "**/*", lambda route: gate_request(route, origin, page, observation)
                )
                await context.route_web_socket(
                    "**", lambda socket: block_socket(socket, observation)
                )
                await page.clock.set_fixed_time(datetime.fromisoformat(frozen_time))
                await page.goto(url, wait_until="load", timeout=timeout_ms)
                selected = page.locator(selector) if selector else None
                if selected is not None:
                    await selected.first.wait_for(state="visible", timeout=timeout_ms)
                    bounding = await selected.first.bounding_box()
                image = await (selected.first if selected else page).screenshot(
                    animations="disabled", caret="hide", timeout=timeout_ms
                )
                save("probe.png", "screenshot", image)
                snapshot = await page.locator("body").aria_snapshot(timeout=timeout_ms)
                save(
                    "probe.ax.json",
                    "ax_snapshot",
                    canonical_json(
                        {"format": "playwright-aria/1", "snapshot": redact_string(snapshot)}
                    ),
                )
                save("probe.dom.html", "dom", redact_string(await page.content()).encode())
                if reference is not None:
                    comparison = compare_rgb(
                        read_regular(reference, 20 * 1024**2),
                        image,
                        rgb_tolerance=0,
                        max_mismatch_ppm=0,
                    )
                    save("probe.diff.png", "diff", comparison.diff_png)
                    if not comparison.passed:
                        observation.record("rgb_mismatch")
        except Exception as error:
            reason = type(error).__name__
            observation.record("probe_failed", reason)
        finally:
            observation.closing = True
            try:
                async with asyncio.timeout(10):
                    if context is not None:
                        await context.close()
                    await browser.close()
                cleanup = True
            except Exception:
                reason = "cleanup_failed"
    save(
        "probe.errors.json",
        "data",
        canonical_json({"errors": observation.errors, "reason_code": reason}),
    )
    result: Record = {
        "status": "ready" if cleanup and reason is None and not observation.errors else "blocked",
        "cleanup_complete": cleanup,
        "viewport": {"width": viewport[0], "height": viewport[1]},
        "bounding_box": bounding,
        "selector": selector,
        "frozen_time": frozen_time,
        "environment": environment,
        "environment_sha256": record_digest(environment),
        "artifacts": artifacts,
        "errors": observation.errors,
    }
    atomic_write(output / "probe.receipt.json", canonical_json(result))
    return result


def register_reference(
    store: VerifiedChangeStore,
    case_id: str,
    receipt: Record,
    output: Path,
    path: str,
    *,
    check_id: str | None = None,
) -> Record:
    if (
        receipt.get("status") != "ready"
        or not receipt.get("cleanup_complete")
        or not safe_path(path)
    ):
        raise ValueError("invalid_reference_observation")
    original = store.case(case_id)
    payloads = {
        i["path"]: read_regular(
            store.path_for("case", case_id) / "inputs" / i["path"], i["size_bytes"]
        )
        for i in original["inputs"]
    }
    plan = decode_json(payloads["criteria/execution.json"])
    environment = decode_json(payloads[plan["environment_path"]])
    if receipt.get("frozen_time") != plan["frozen_time"]:
        raise ValueError("reference_time_mismatch")
    if receipt["environment_sha256"] != record_digest(environment):
        raise ValueError("reference_environment_mismatch")
    candidates = [
        c
        for c in original["checks"]
        if c["kind"] in {"browser", "visual"}
        and c["viewport"] == receipt["viewport"]
        and (check_id is None or c["check_id"] == check_id)
    ]
    if len(candidates) != 1:
        raise ValueError("reference_check_selection_required")
    check = candidates[0]
    data = read_regular(output / "probe.png", original["limits"]["max_file_bytes"])
    observation = next(a for a in receipt["artifacts"] if a["kind"] == "screenshot")
    if hashlib.sha256(data).hexdigest() != observation["sha256"]:
        raise ValueError("reference_hash_mismatch")
    if path in payloads:
        raise ValueError("reference_path_exists")
    payloads[path] = data
    flow = decode_json(payloads[check["definition_path"]])
    flow["steps"].append(
        {
            "step_id": "reference-" + uuid4().hex,
            "action": "snapshot",
            "selector": {"strategy": "css", "value": receipt["selector"], "name": None}
            if receipt.get("selector")
            else None,
            "value": None,
            "count": None,
            "reference_path": path,
            "rgb_tolerance": 0,
            "max_mismatch_ppm": 0,
            "timeout_ms": 5000,
        }
    )
    payloads[check["definition_path"]] = canonical_json(flow)
    plan["visual_references"].append(
        {
            "path": path,
            "viewport": receipt["viewport"],
            "environment_sha256": receipt["environment_sha256"],
            "mask_sha256": None,
        }
    )
    payloads["criteria/execution.json"] = canonical_json(plan)
    case = copy.deepcopy(original)
    case.update(case_id=str(uuid4()), supersedes_case_id=case_id, created_at=record_time())
    case["checks"] = [
        {
            **c,
            "kind": "visual",
            "definition_sha256": hashlib.sha256(payloads[c["definition_path"]]).hexdigest(),
        }
        if c["check_id"] == check["check_id"]
        else c
        for c in case["checks"]
    ]
    case["inputs"].append(
        {
            "path": path,
            "role": "reference",
            "sha256": hashlib.sha256(data).hexdigest(),
            "mode": 0o644,
            "size_bytes": len(data),
        }
    )
    for item in case["inputs"]:
        item.update(
            sha256=hashlib.sha256(payloads[item["path"]]).hexdigest(),
            size_bytes=len(payloads[item["path"]]),
        )
    case["evaluator_sha256"] = manifest_digest(
        SnapshotFile(i["path"], payloads[i["path"]], i["sha256"], i["mode"], i["size_bytes"])
        for i in case["inputs"]
        if i["role"] == "criteria"
    )
    return store.publish_case(case, payloads)

"""Host-owned checker entry point, copied into the read-only criteria mount."""

from __future__ import annotations

import asyncio
import hashlib
import platform
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Literal, cast

from playwright.async_api import async_playwright

from ddk.adapters.verified_browser import BrowserSettings, VisualReference, run_flow
from ddk.models.verified_change import Record, canonical_json, decode_json, record_digest, safe_path
from ddk.security.file_access import read_regular

PORT = 4173


async def wait_for_preview(deadline_ns: int, *, port: int = PORT) -> None:
    while time.monotonic_ns() < deadline_ns:
        try:
            async with asyncio.timeout(min(0.2, (deadline_ns - time.monotonic_ns()) / 1e9)):
                _, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.close()
                await writer.wait_closed()
                return
        except (OSError, TimeoutError):
            await asyncio.sleep(min(0.05, max(0, (deadline_ns - time.monotonic_ns()) / 1e9)))
    raise ValueError("preview_unavailable")


def font_manifest() -> str:
    answer = subprocess.run(
        ["fc-list", "--format", "%{file}\\n"], capture_output=True, check=True, timeout=10
    )
    if len(answer.stdout) > 1024 * 1024:
        raise ValueError("font_manifest_limit")
    paths = sorted(set(answer.stdout.decode("utf-8", errors="strict").splitlines()))
    if not paths or len(paths) > 2000:
        raise ValueError("font_manifest_unavailable")
    rows: list[Record] = []
    total = 0
    for name in paths:
        path = Path(name)
        if not path.is_absolute():
            raise ValueError("invalid_font_path")
        data = read_regular(path.resolve(), 32 * 1024**2)
        total += len(data)
        if total > 200 * 1024**2:
            raise ValueError("font_manifest_limit")
        rows.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
    return hashlib.sha256(canonical_json(rows)).hexdigest()


async def probe(executable: str | None) -> Record:
    async with async_playwright() as playwright:
        binary = executable or playwright.chromium.executable_path
        digest = hashlib.sha256()
        with Path(binary).open("rb") as source:
            while block := source.read(1024 * 1024):
                digest.update(block)
        browser = await playwright.chromium.launch(
            headless=True, chromium_sandbox=True, executable_path=binary, timeout=10_000
        )
        try:
            browser_version = browser.version
        finally:
            await browser.close()
    return {
        "os_name": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "playwright_version": version("playwright"),
        "browser_version": browser_version,
        "browser_binary_sha256": digest.hexdigest(),
        "font_manifest_sha256": font_manifest(),
    }


async def execute(payload: Record) -> Record:
    if payload.get("mode") == "probe":
        return await probe(payload["browser_executable"])
    if payload.get("mode") != "flow":
        raise ValueError("invalid_worker_mode")
    deadline = time.monotonic_ns() + payload["timeout_ms"] * 1_000_000
    await wait_for_preview(deadline)
    root = Path("/criteria/inputs")
    plan, environment, check = payload["plan"], payload["environment"], payload["check"]
    references: dict[str, VisualReference] = {}
    for row in plan["visual_references"]:
        name = row["path"]
        if not safe_path(name):
            raise ValueError("unsafe_reference_path")
        data = read_regular(root / name, payload["max_artifact_bytes"])
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
        references[name] = VisualReference(
            data,
            hashlib.sha256(data).hexdigest(),
            width,
            height,
            (row["viewport"]["width"], row["viewport"]["height"]),
            row["environment_sha256"],
            row["mask_sha256"],
        )
    if not safe_path(check["definition_path"]):
        raise ValueError("unsafe_definition_path")
    result = await run_flow(
        read_regular(root / check["definition_path"], 2 * 1024**2),
        check=check,
        base_url=f"http://127.0.0.1:{PORT}",
        output_dir=Path("/results"),
        fixture_sha256=environment["fixture_sha256"],
        references=references,
        settings=BrowserSettings(
            environment,
            record_digest(environment),
            plan["frozen_time"],
            executable_path=plan["browser_executable"],
            cleanup_timeout_ms=payload["cleanup_timeout_ms"],
            max_artifact_bytes=payload["max_artifact_bytes"],
        ),
        phase=cast(Literal["baseline", "candidate"], payload["phase"]),
        deadline_ns=deadline,
    )
    return {
        "result": result.result,
        "artifacts": result.artifacts,
        "cleanup_complete": result.cleanup_complete,
    }


def main() -> None:
    payload = decode_json(sys.stdin.buffer.read(2 * 1024**2 + 1))
    sys.stdout.buffer.write(canonical_json(asyncio.run(execute(payload))) + b"\n")

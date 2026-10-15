"""Fixed browser criteria and RGB thresholds are checked before execution."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from ddk.adapters.verified_browser import BrowserSettings, compare_rgb, run_flow
from ddk.models.verified_change import canonical_json, record_digest

FIXTURE = "a" * 64


def png(color: tuple[int, int, int], size: tuple[int, int] = (12, 12)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, color).save(output, format="PNG")
    return output.getvalue()


def environment() -> dict[str, Any]:
    examples = json.loads(Path("tests/fixtures/verified-change/contract-examples.json").read_text())
    return next(
        entry["record"]
        for entry in examples["valid"]
        if entry["record"].get("record_type") == "environment"
    )


def step(action: str, **values: Any) -> dict[str, Any]:
    return {
        "step_id": values.pop("step_id", action),
        "action": action,
        "selector": None,
        "value": None,
        "count": None,
        "reference_path": None,
        "rgb_tolerance": None,
        "max_mismatch_ppm": None,
        "timeout_ms": 500,
        **values,
    }


def criteria(steps: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    payload = canonical_json(
        {
            "record_type": "flow",
            "schema_version": "verified-change/1",
            "flow_id": "preserve",
            "check_id": "check-preserve",
            "entry_path": "/",
            "fixture_sha256": FIXTURE,
            "steps": steps,
        }
    )
    return payload, {
        "check_id": "check-preserve",
        "role": "preserve",
        "required": True,
        "kind": "browser",
        "definition_path": "criteria/preserve.json",
        "definition_sha256": hashlib.sha256(payload).hexdigest(),
        "command_argv": [],
        "viewport": {"width": 320, "height": 200},
        "timeout_ms": 5000,
    }


def test_rgb_detects_color_change_even_when_luminance_ssim_passes() -> None:
    result = compare_rgb(png((255, 0, 0)), png((0, 130, 0)), rgb_tolerance=0, max_mismatch_ppm=0)

    assert not result.passed
    assert result.mismatch_ppm == 1_000_000
    assert result.ssim > 0.99


def test_rgb_uses_exact_approved_component_threshold_and_ratio() -> None:
    assert compare_rgb(png((1, 2, 3)), png((3, 4, 5)), rgb_tolerance=2, max_mismatch_ppm=0).passed
    assert not compare_rgb(
        png((1, 2, 3)), png((4, 4, 5)), rgb_tolerance=2, max_mismatch_ppm=0
    ).passed


def test_size_difference_cannot_be_resized_into_a_pass() -> None:
    with pytest.raises(ValueError, match="image_size_mismatch"):
        compare_rgb(png((0, 0, 0)), png((0, 0, 0), (13, 12)), rgb_tolerance=0, max_mismatch_ppm=0)


@pytest.mark.parametrize("fault", ["criteria", "fixture", "environment", "external", "script"])
async def test_invalid_inputs_never_start_a_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    env = environment()
    env["fixture_sha256"] = FIXTURE
    steps = [step("expect-url", value="/")]
    if fault == "external":
        steps = [step("goto", value="//example.org/")]
    elif fault == "script":
        steps = [step("evaluate", value="alert(1)")]
    payload, check = criteria(steps)
    if fault == "criteria":
        check["definition_sha256"] = "0" * 64
    settings = BrowserSettings(
        environment=env,
        environment_sha256="0" * 64 if fault == "environment" else record_digest(env),
        frozen_time="2026-10-14T00:00:00+00:00",
    )

    def forbidden() -> None:
        raise AssertionError("browser must not start")

    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", forbidden)
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path,
        fixture_sha256="b" * 64 if fault == "fixture" else FIXTURE,
        references={},
        settings=settings,
    )
    assert result.result["status"] == "unavailable"
    assert result.cleanup_complete
    assert result.result["evidence_origin"] == "trusted-observer"


async def test_cancellation_during_cleanup_is_propagated_after_closing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    begun, finish = asyncio.Event(), asyncio.Event()

    class Resource:
        @property
        def chromium(self) -> None:
            raise RuntimeError("synthetic setup failure")

        async def close(self) -> None:
            begun.set()
            await finish.wait()

    resource = Resource()
    monkeypatch.setattr(
        "ddk.adapters.verified_browser.async_playwright",
        lambda: SimpleNamespace(
            start=AsyncMock(return_value=resource), __aexit__=AsyncMock(side_effect=resource.close)
        ),
    )
    env = environment()
    env["fixture_sha256"] = FIXTURE
    payload, check = criteria([step("expect-url", value="/")])
    task = asyncio.create_task(
        run_flow(
            payload,
            check=check,
            base_url="http://127.0.0.1:1234",
            output_dir=tmp_path,
            fixture_sha256=FIXTURE,
            references={},
            settings=BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00"),
        )
    )
    await asyncio.wait_for(begun.wait(), timeout=1)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancelled_driver_start_is_owned_and_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    begun, closed = asyncio.Event(), asyncio.Event()

    class Manager:
        async def start(self) -> None:
            begun.set()
            await asyncio.Event().wait()

        async def __aexit__(self) -> None:
            closed.set()

    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", Manager)
    env = environment()
    env["fixture_sha256"] = FIXTURE
    payload, check = criteria([step("expect-url", value="/")])
    task = asyncio.create_task(
        run_flow(
            payload,
            check=check,
            base_url="http://127.0.0.1:1234",
            output_dir=tmp_path,
            fixture_sha256=FIXTURE,
            references={},
            settings=BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00"),
        )
    )
    await asyncio.wait_for(begun.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()


async def test_expired_monotonic_deadline_cannot_start_browser(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[bool] = []

    def forbidden() -> None:
        started.append(True)
        raise AssertionError("expired")

    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", forbidden)
    env = environment()
    env["fixture_sha256"] = FIXTURE
    payload, check = criteria([step("expect-url", value="/")])
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00"),
        deadline_ns=0,
    )
    assert not started
    assert result.result["reason_code"] == "timeout"


@pytest.mark.parametrize(
    "failure", [RuntimeError("sandbox unavailable"), PlaywrightTimeoutError("launch timeout")]
)
async def test_sandbox_failure_never_retries_with_weaker_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    from importlib.metadata import version
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    binary = tmp_path / "pinned-browser"
    binary.write_bytes(b"pinned")
    launch = AsyncMock(side_effect=failure)
    browser_type = SimpleNamespace(executable_path=str(binary), launch=launch)
    manager = SimpleNamespace(
        start=AsyncMock(return_value=SimpleNamespace(chromium=browser_type)), __aexit__=AsyncMock()
    )
    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", lambda: manager)
    env = environment()
    env["fixture_sha256"] = FIXTURE
    env["playwright_version"] = version("playwright")
    env["browser_binary_sha256"] = hashlib.sha256(b"pinned").hexdigest()
    payload, check = criteria([step("expect-url", value="/")])
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path / "output",
        fixture_sha256=FIXTURE,
        references={},
        settings=BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00"),
    )
    assert result.result["status"] == "unavailable"
    assert launch.await_count == 1
    assert launch.call_args.kwargs["headless"] is True
    assert launch.call_args.kwargs["chromium_sandbox"] is True
    assert launch.call_args.kwargs["args"] == [
        "--hide-scrollbars",
        "--mute-audio",
        "--force-color-profile=srgb",
    ]
    manager.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("fault", ["missing", "hash", "environment", "viewport", "size", "mask"])
async def test_reference_must_match_approved_conditions_before_browser_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from dataclasses import replace

    from ddk.adapters.verified_browser import VisualReference

    env = environment()
    env["fixture_sha256"] = FIXTURE
    settings = BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00")
    image = png((255, 0, 0))
    reference = VisualReference(
        image, hashlib.sha256(image).hexdigest(), 12, 12, (320, 200), settings.environment_sha256
    )
    changes: dict[str, Any] = {
        "hash": {"sha256": "0" * 64},
        "environment": {"environment_sha256": "0" * 64},
        "viewport": {"viewport": (640, 480)},
        "size": {"width": 13},
        "mask": {"mask_sha256": "0" * 64},
    }
    references = (
        {} if fault == "missing" else {"references/fixed.png": replace(reference, **changes[fault])}
    )
    payload, check = criteria(
        [
            step(
                "snapshot",
                reference_path="references/fixed.png",
                rgb_tolerance=0,
                max_mismatch_ppm=0,
            )
        ]
    )

    def forbidden() -> None:
        raise AssertionError("reference was not approved")

    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", forbidden)
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references=references,
        settings=settings,
    )
    assert result.result["status"] == "unavailable"
    assert result.result["reason_code"].startswith(("reference_", "mask_"))


async def test_incomplete_cleanup_is_bounded_and_never_passes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    import time
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    async def close_forever() -> None:
        await asyncio.Event().wait()

    manager = SimpleNamespace(
        start=AsyncMock(side_effect=RuntimeError("setup failed")),
        __aexit__=AsyncMock(side_effect=close_forever),
    )
    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", lambda: manager)
    env = environment()
    env["fixture_sha256"] = FIXTURE
    payload, check = criteria([step("expect-url", value="/")])
    started = time.monotonic_ns()
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=BrowserSettings(
            env, record_digest(env), "2026-10-14T00:00:00+00:00", cleanup_timeout_ms=20
        ),
    )
    assert (time.monotonic_ns() - started) / 1e9 < 0.5
    assert not result.cleanup_complete
    assert result.result["status"] == "unavailable"
    assert result.result["reason_code"] == "cleanup_failed"


def test_malformed_browser_text_cannot_erase_a_console_error() -> None:
    from ddk.adapters.verified_browser import _Observation

    observation = _Observation()
    observation.record("console_error", "unpaired: " + chr(0xD800))
    assert observation.errors[0]["code"] == "console_error"
    assert canonical_json({"errors": observation.errors})


async def test_visual_check_without_snapshot_cannot_pass_as_visual_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden() -> None:
        raise AssertionError("visual criteria missing")

    monkeypatch.setattr("ddk.adapters.verified_browser.async_playwright", forbidden)
    env = environment()
    env["fixture_sha256"] = FIXTURE
    payload, check = criteria([step("expect-url", value="/")])
    check["kind"] = "visual"
    result = await run_flow(
        payload,
        check=check,
        base_url="http://127.0.0.1:1234",
        output_dir=tmp_path,
        fixture_sha256=FIXTURE,
        references={},
        settings=BrowserSettings(env, record_digest(env), "2026-10-14T00:00:00+00:00"),
    )
    assert result.result["status"] == "unavailable"
    assert result.result["reason_code"] == "visual_steps_missing"

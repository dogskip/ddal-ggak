"""A recorded proposal must pass the real headless regression flow before apply."""

from __future__ import annotations

from uuid import uuid4

import pytest

from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.models.verified_change import record_digest
from ddk.services.source_snapshot import capture_source
from ddk.services.verified_budget import ProviderResult, ProviderUsage
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_service import VerifiedChangeService
from ddk.services.verified_repair import RepairReply
from tests.e2e.test_verified_browser import settings as settings
from tests.e2e.test_verified_evaluator import scenario
from tests.public_contract import public_payload
from tests.unit.test_verified_budget import price
from tests.unit.test_verified_change_engine import RUN_ID
from tests.unit.test_verified_repair import REPAIR_ID

pytestmark = pytest.mark.playwright


async def test_real_browser_repair_preserves_navigation_and_applies_only_ready(tmp_path, settings):
    case, store, snapshots = scenario(tmp_path, settings, "regression")
    source = await VerifiedChangeEngine(
        store, VerifiedEvaluator(trusted_local_approved=True)
    ).verify(
        case["case_id"],
        baseline=tmp_path / "baseline",
        candidate=tmp_path / "candidate",
        run_id=RUN_ID,
        change_requirements={"index.html": ["target"]},
    )
    assert source["decision"] == "blocked"
    attempts = []

    async def recorded(request):
        import json

        attempts.append(request)
        content = (
            "<!doctype html><link rel='icon' href='data:,'><h1>New</h1><a href='/next'>Continue</a>"
        )
        payload = json.dumps({"files": [{"path": "index.html", "content": content}]})
        return ProviderResult(
            RepairReply(payload, output_bytes=len(payload.encode())),
            ProviderUsage(1, 1, 0),
            "anthropic",
            "claude-sonnet-5-5",
        )

    service = VerifiedChangeService(
        store.repository, evaluator=VerifiedEvaluator(trusted_local_approved=True)
    )
    result = await service.repair(
        RUN_ID,
        baseline=tmp_path / "baseline",
        candidate=tmp_path / "candidate",
        run_id=REPAIR_ID,
        price=price(source),
        input_limit=8192,
        output_limit=2048,
        provider=recorded,
        provider_approved=True,
        trusted_local_approved=True,
    )
    assert result["decision"] == "ready", result["actions"]
    assert result["assurance"] == "trusted-local"
    assert result["latest_round"] == 1
    assert len(attempts) == 1
    assert all(r["status"] == "passed" for r in result["results"] if r["round_no"] == 1)
    assert any(a["kind"] == "screenshot" for a in result["artifacts"])
    for name, snapshot in snapshots.items():
        assert capture_source(tmp_path / name).tree_sha256 == snapshot.tree_sha256
    for item in snapshots["baseline"].files:
        target = store.repository / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
        target.chmod(item.mode)
    applied = service.apply(
        apply_id=str(uuid4()),
        case_id=case["case_id"],
        run_id=REPAIR_ID,
        run_sha256=record_digest(result),
        changes_sha256=record_digest(result["changes"]),
        quiescence_confirmed=True,
        local_storage_confirmed=True,
        required_assurance="trusted-local",
    )
    assert applied["state"] == "applied"
    assert b"New" in (store.repository / "index.html").read_bytes()
    assert b"Continue" in (store.repository / "index.html").read_bytes()


def test_cli_repair_and_apply_with_real_headless_checks(tmp_path, monkeypatch):
    import asyncio
    import json
    from dataclasses import asdict

    from typer.testing import CliRunner

    from ddk.cli import app, verified

    config = asyncio.run(settings.__wrapped__())
    case, store, originals = scenario(tmp_path, config, "regression")
    runner = CliRunner()
    requirements = tmp_path / "requirements.json"
    requirements.write_text('{"index.html":["target"]}')
    common = ["--repo", str(store.repository), "--json"]
    checked = runner.invoke(
        app,
        [
            "change",
            "verify",
            "--case-id",
            case["case_id"],
            "--run-id",
            RUN_ID,
            "--baseline",
            str(tmp_path / "baseline"),
            "--candidate",
            str(tmp_path / "candidate"),
            "--change-requirements",
            str(requirements),
            "--trusted-local",
            *common,
        ],
    )
    assert checked.exit_code == 1, checked.output
    source = public_payload(checked.stdout)
    assert source["decision"] == "blocked"
    pricing = tmp_path / "price.json"
    pricing.write_text(json.dumps(asdict(price(source))))
    calls = []

    async def recorded(request):
        calls.append(request)
        text = json.dumps(
            {
                "files": [
                    {
                        "path": "index.html",
                        "content": (
                            "<!doctype html><link rel='icon' href='data:,'><h1>New</h1>"
                            "<a href='/next'>Continue</a>"
                        ),
                    }
                ]
            }
        )
        return ProviderResult(
            RepairReply(text, output_bytes=len(text.encode())),
            ProviderUsage(1, 1, 0),
            "anthropic",
            "claude-sonnet-5-5",
        )

    monkeypatch.setattr(verified, "_repair_provider", lambda: recorded)
    repaired = runner.invoke(
        app,
        [
            "change",
            "repair",
            "--source-run-id",
            RUN_ID,
            "--run-id",
            REPAIR_ID,
            "--baseline",
            str(tmp_path / "baseline"),
            "--candidate",
            str(tmp_path / "candidate"),
            "--price",
            str(pricing),
            "--input-token-limit",
            "8192",
            "--output-token-limit",
            "2048",
            "--confirm-provider",
            "--trusted-local",
            *common,
        ],
    )
    assert repaired.exit_code == 0, repaired.output
    result = public_payload(repaired.stdout)
    assert result["decision"] == "ready" and len(calls) == 1
    for name, snapshot in originals.items():
        assert capture_source(tmp_path / name).tree_sha256 == snapshot.tree_sha256
    for item in originals["baseline"].files:
        target = store.repository / item.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.content)
        target.chmod(item.mode)
    applied = runner.invoke(
        app,
        [
            "change",
            "apply",
            "--case-id",
            case["case_id"],
            "--run-id",
            REPAIR_ID,
            "--run-sha256",
            record_digest(result),
            "--changes-sha256",
            record_digest(result["changes"]),
            "--confirm-local-storage",
            "--confirm-quiescence",
            "--required-assurance",
            "trusted-local",
            *common,
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert public_payload(applied.stdout)["state"] == "applied"
    assert b">Continue<" in (store.repository / "index.html").read_bytes()

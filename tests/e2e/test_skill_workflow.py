"""A recorded plan invokes the real CLI without host or provider execution."""

from __future__ import annotations

import asyncio
import json

from typer.testing import CliRunner

from ddk.adapters.llm.base import LLMCallConfig, Message
from ddk.adapters.llm.recording import RecordingLLMAdapter, ReplayLLMAdapter
from ddk.cli import app
from ddk.installer import ASSETS
from tests.fakes.fake_llm_adapter import FakeLLMAdapter
from tests.unit.test_case_bootstrapper import setup_repo


async def test_recorded_verify_skill_dry_run_keeps_execution_unapproved(tmp_path):
    repository = tmp_path / "repo"
    repository.mkdir()
    setup_repo(repository)
    instructions = (ASSETS / "ddk-verify/SKILL.md").read_text()
    cassette = tmp_path / "plan.json"
    args = ["up", "Fix heading", "--repo", str(repository), "--dry-run", "--json"]
    recorder = RecordingLLMAdapter(
        FakeLLMAdapter({"skill": json.dumps(args)}), cassette_path=cassette
    )
    messages = [
        Message("system", "skill\n" + instructions),
        Message("user", "Inspect the verification plan only."),
    ]
    config = LLMCallConfig(model="recorded", metadata={"purpose": "skill-plan"})
    await recorder.complete(messages, config)
    recorder.save()
    response = await ReplayLLMAdapter.load(cassette).complete(messages, config)
    invocation = json.loads(response.content)
    assert invocation == args
    assert not {"--trusted-local", "--repair", "--confirm-provider", "--apply"}.intersection(
        invocation
    )
    result = await asyncio.to_thread(CliRunner().invoke, app, invocation)
    assert result.exit_code == 0, result.output
    record = json.loads(result.stdout)
    assert record["dry_run"] is True
    assert record["status"] == "blocked"
    assert record["actions"]
    assert not (repository / ".ddk").exists()
    assert response.cost_usd == 0

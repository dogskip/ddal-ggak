"""Behavior tests for all 8 test doubles — INFRA-05."""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.filesystem import FilesystemPort
from ddk.adapters.llm.base import LLMAdapter, LLMCallConfig, Message
from ddk.adapters.playwright_browser import PlaywrightAdapter
from tests.fakes.fake_cost_tracker import FakeCostTracker
from tests.fakes.fake_fallback_chain import FakeFallbackChain
from tests.fakes.fake_filesystem import InMemoryFilesystem
from tests.fakes.fake_llm_adapter import FakeLLMAdapter
from tests.fakes.fake_playwright_adapter import FakePlaywrightAdapter
from tests.fakes.fake_rollback import FakeRollbackController
from tests.fakes.fake_sandbox import TempDirSandbox
from tests.fakes.fake_subprocess import FakeSubprocessRunner


class TestFakeLLMAdapter:
    async def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeLLMAdapter(), LLMAdapter)

    async def test_returns_canned_response(self) -> None:
        fake = FakeLLMAdapter(responses={"hello": "world"})
        msgs = [Message(role="system", content="hello there")]
        result = await fake.complete(msgs, LLMCallConfig())
        assert result.content == "world"

    async def test_records_call_log(self) -> None:
        fake = FakeLLMAdapter(responses={"test": "ok"})
        msgs = [Message(role="system", content="test prompt")]
        await fake.complete(msgs, LLMCallConfig())
        assert len(fake.call_log) == 1
        assert fake.call_log[0]["key"] == "test"

    async def test_raises_on_missing_key(self) -> None:
        fake = FakeLLMAdapter(responses={})
        msgs = [Message(role="system", content="unknown prompt")]
        with pytest.raises(ValueError, match="no fixture for key"):
            await fake.complete(msgs, LLMCallConfig())

    async def test_dict_response_becomes_json(self) -> None:
        fake = FakeLLMAdapter(responses={"data": {"key": "value"}})
        msgs = [Message(role="system", content="data payload")]
        result = await fake.complete(msgs, LLMCallConfig())
        assert '"key"' in result.content


class TestInMemoryFilesystem:
    def test_satisfies_protocol(self) -> None:
        assert isinstance(InMemoryFilesystem(), FilesystemPort)

    def test_write_then_read(self) -> None:
        fs = InMemoryFilesystem()
        fs.write_text(Path("/app/test.txt"), "hello")
        assert fs.read_text(Path("/app/test.txt")) == "hello"

    def test_read_nonexistent_raises(self) -> None:
        fs = InMemoryFilesystem()
        with pytest.raises(FileNotFoundError):
            fs.read_text(Path("/no/such/file"))

    def test_exists(self) -> None:
        fs = InMemoryFilesystem()
        assert fs.exists(Path("/app/test.txt")) is False
        fs.write_text(Path("/app/test.txt"), "data")
        assert fs.exists(Path("/app/test.txt")) is True

    def test_list_dir(self) -> None:
        fs = InMemoryFilesystem()
        fs.write_text(Path("/app/a.txt"), "a")
        fs.write_text(Path("/app/b.txt"), "b")
        listing = fs.list_dir(Path("/app"))
        assert len(listing) >= 2

    def test_mkdir(self) -> None:
        fs = InMemoryFilesystem()
        fs.mkdir(Path("/app/deep/nested"), parents=True)
        assert fs.exists(Path("/app/deep/nested")) is True

    def test_read_write_bytes(self) -> None:
        fs = InMemoryFilesystem()
        fs.write_bytes(Path("/app/image.png"), b"\x89PNG")
        assert fs.read_bytes(Path("/app/image.png")) == b"\x89PNG"

    def test_read_bytes_nonexistent_raises(self) -> None:
        fs = InMemoryFilesystem()
        with pytest.raises(FileNotFoundError):
            fs.read_bytes(Path("/no/such/file"))


class TestTempDirSandbox:
    async def test_create_and_cleanup(self, tmp_path: Path) -> None:
        sandbox = TempDirSandbox()
        sandbox_path = await sandbox.create(tmp_path)
        assert sandbox_path.exists()
        await sandbox.cleanup()
        assert not sandbox_path.exists()

    async def test_run_command(self, tmp_path: Path) -> None:
        sandbox = TempDirSandbox()
        await sandbox.create(tmp_path)
        result = await sandbox.run_command(["echo", "hello"])
        assert result.returncode == 0
        await sandbox.cleanup()


class TestFakeSubprocessRunner:
    async def test_satisfies_protocol(self) -> None:
        assert isinstance(FakeSubprocessRunner(), BuildRunner)

    async def test_default_success(self) -> None:
        runner = FakeSubprocessRunner(default_success=True)
        result = await runner.run(["npm", "run", "build"], Path("/app"))
        assert result.success is True
        assert result.returncode == 0

    async def test_default_failure(self) -> None:
        runner = FakeSubprocessRunner(default_success=False)
        result = await runner.run(["npm", "test"], Path("/app"))
        assert result.success is False
        assert result.returncode == 1

    async def test_records_commands(self) -> None:
        runner = FakeSubprocessRunner()
        await runner.run(["npm", "install"], Path("/app"))
        assert len(runner.run_log) == 1
        assert runner.run_log[0]["command"] == ["npm", "install"]


class TestFakePlaywrightAdapter:
    async def test_satisfies_protocol(self) -> None:
        assert isinstance(FakePlaywrightAdapter(), PlaywrightAdapter)

    async def test_returns_screenshot_path(self) -> None:
        fake = FakePlaywrightAdapter(screenshot_path=Path("/tmp/shot.png"))
        result = await fake.capture_screenshot("http://localhost:3000", Path("/out/shot.png"))
        assert result == Path("/tmp/shot.png")

    async def test_close(self) -> None:
        fake = FakePlaywrightAdapter()
        await fake.close()
        assert fake._closed is True


class TestFakeFallbackChain:
    async def test_fails_then_succeeds(self) -> None:
        chain = FakeFallbackChain(fail_count=2, success_content="recovered")
        msgs = [Message(role="user", content="test")]
        config = LLMCallConfig()

        with pytest.raises(ConnectionError):
            await chain.complete(msgs, config)
        with pytest.raises(ConnectionError):
            await chain.complete(msgs, config)

        result = await chain.complete(msgs, config)
        assert result.content == "recovered"
        assert chain.attempt == 3


class TestFakeRollbackController:
    async def test_create_and_rollback(self) -> None:
        ctrl = FakeRollbackController()
        commit = await ctrl.create_checkpoint(Path("/repo"), "refs/ddk/fix/C-001/attempt-1")
        assert commit.startswith("fake-")
        await ctrl.rollback_to(Path("/repo"), "refs/ddk/fix/C-001/attempt-1")
        assert len(ctrl.rollback_log) == 1

    async def test_rollback_missing_raises(self) -> None:
        ctrl = FakeRollbackController()
        with pytest.raises(ValueError, match="Checkpoint not found"):
            await ctrl.rollback_to(Path("/repo"), "nonexistent")


class TestFakeCostTracker:
    def test_always_zero_cost(self) -> None:
        tracker = FakeCostTracker()
        cost = tracker.record_call("anthropic", "claude-3-5-sonnet", 1000, 500)
        assert cost == 0.0
        assert tracker.get_total_cost() == 0.0
        assert len(tracker.recorded_calls) == 1


# --- Chaos Fixtures ---


class TestChaosFixtures:
    """Fault path testing with malformed/rate-limit/extra-field responses."""

    async def test_malformed_json_response(self) -> None:
        """FakeLLM returns invalid JSON — downstream must handle gracefully."""
        fake = FakeLLMAdapter(responses={"parse": "{{not valid json{{"})
        msgs = [Message(role="system", content="parse this")]
        result = await fake.complete(msgs, LLMCallConfig())
        # The response is returned as-is; parsing is caller's responsibility
        assert "not valid json" in result.content

    async def test_rate_limit_simulation(self) -> None:
        """FakeFallbackChain simulates rate limit via ConnectionError."""
        chain = FakeFallbackChain(fail_count=3, success_content="ok")
        msgs = [Message(role="user", content="test")]
        config = LLMCallConfig()
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await chain.complete(msgs, config)

    async def test_extra_fields_in_response(self) -> None:
        """FakeLLM returns extra fields — DDKBaseModel with extra=forbid should reject."""
        from pydantic import ValidationError

        from ddk.models.input import CaseInput

        extra_json = (
            '{"case_id": "C-001", "image_paths": ["/img.png"],'
            ' "prompt": "test", "repo_path": "/repo",'
            ' "extra_field": "bad"}'
        )
        fake = FakeLLMAdapter(responses={"extra": extra_json})
        msgs = [Message(role="system", content="extra fields test")]
        result = await fake.complete(msgs, LLMCallConfig())
        with pytest.raises(ValidationError):
            CaseInput.model_validate_json(result.content)

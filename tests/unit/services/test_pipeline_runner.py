"""Tests for PipelineRunner service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ddk.services.pipeline_runner import PipelineRunner, RuntimeServices


class TestRuntimeServices:
    def test_create(self) -> None:
        svc = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
        )
        assert svc.llm is not None
        assert svc.filesystem is not None


class TestPipelineRunner:
    def test_init(self) -> None:
        services = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
        )
        runner = PipelineRunner(services=services)
        assert runner._services is services

    @pytest.mark.asyncio
    async def test_run_case_invokes_graph(self) -> None:
        services = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
        )
        runner = PipelineRunner(services=services)

        mock_case = MagicMock()
        mock_case.repo_path = "/tmp/test-repo"
        mock_case.case_id = "C-001"

        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(
            return_value={"terminal_state": "certified"},
        )
        mock_graph_fn = MagicMock()
        mock_graph_fn.return_value.compile.return_value = mock_compiled

        mock_module = MagicMock()
        mock_module.build_ddk_graph = mock_graph_fn

        with patch(
            "ddk.services.pipeline_runner.import_module",
            return_value=mock_module,
        ):
            result = await runner.run_case(mock_case)

        assert result["terminal_state"] == "certified"
        assert result["llm_calls"] == []
        mock_compiled.ainvoke.assert_called_once()


class TestRuntimeSettingsReachTheGraph:
    @staticmethod
    def _services(**overrides: object) -> RuntimeServices:
        return RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
            **overrides,  # type: ignore[arg-type]
        )

    @staticmethod
    async def _run(services: RuntimeServices) -> tuple[MagicMock, MagicMock]:
        mock_compiled = MagicMock()
        mock_compiled.ainvoke = AsyncMock(return_value={})
        mock_module = MagicMock()
        mock_module.build_ddk_graph.return_value.compile.return_value = mock_compiled
        case = MagicMock()
        case.repo_path = "/tmp/test-repo"
        case.case_id = "C-001"

        with (
            patch("ddk.services.pipeline_runner.import_module", return_value=mock_module),
            patch("ddk.services.pipeline_runner.RuntimeValidator") as validator_cls,
            patch("ddk.services.pipeline_runner.initial_state") as make_state,
        ):
            await PipelineRunner(services).run_case(case)
        return validator_cls, make_state

    async def test_validator_gets_install_and_timeout_settings(self) -> None:
        validator_cls, _ = await self._run(
            self._services(install_dependencies=True, step_timeout_s=42)
        )

        kwargs = validator_cls.call_args.kwargs
        assert kwargs["install_dependencies"] is True
        assert kwargs["step_timeout_s"] == 42

    async def test_defaults_keep_install_off(self) -> None:
        validator_cls, _ = await self._run(self._services())

        assert validator_cls.call_args.kwargs["install_dependencies"] is False

    async def test_fix_attempt_limit_becomes_the_retry_budget(self) -> None:
        _, make_state = await self._run(self._services(max_fix_attempts=5))

        assert make_state.call_args.kwargs["retry_budget"] == 5


class TestAutoFixPlannerWiring:
    async def test_planner_repairs_with_the_primary_model_inside_the_target_repo(self) -> None:
        services = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
            primary_model="primary-model",
            light_model="light-model",
        )
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value={})
        module = MagicMock()
        module.build_ddk_graph.return_value.compile.return_value = compiled
        case = MagicMock()
        case.repo_path = "/tmp/target-repo"
        case.case_id = "C-001"

        with (
            patch("ddk.services.pipeline_runner.import_module", return_value=module),
            patch("ddk.services.pipeline_runner.AutoFixPlanner") as planner_cls,
        ):
            await PipelineRunner(services).run_case(case)

        kwargs = planner_cls.call_args.kwargs
        assert kwargs["model"] == "primary-model"
        assert str(kwargs["repo_root"]) == "/tmp/target-repo"


class TestCallRecording:
    async def test_run_returns_the_recorded_calls_and_gives_nodes_the_recorder(self) -> None:
        from ddk.adapters.llm.base import LLMCallConfig, Message  # noqa: PLC0415
        from tests.fakes.fake_llm_adapter import FakeLLMAdapter  # noqa: PLC0415

        inner = FakeLLMAdapter(responses={"autofix": "x"})
        services = RuntimeServices(
            llm=inner,
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
        )
        seen: dict[str, object] = {}

        async def fake_invoke(state: object, context: object) -> dict[str, object]:
            seen["llm"] = context.llm  # type: ignore[attr-defined]
            await context.llm.complete(  # type: ignore[attr-defined]
                [Message(role="system", content="Autofix it")], LLMCallConfig(model="m")
            )
            return {"terminal_state": "ready"}

        compiled = MagicMock()
        compiled.ainvoke = fake_invoke
        module = MagicMock()
        module.build_ddk_graph.return_value.compile.return_value = compiled
        case = MagicMock()
        case.repo_path = "/tmp/repo"
        case.case_id = "C-001"

        with patch("ddk.services.pipeline_runner.import_module", return_value=module):
            result = await PipelineRunner(services).run_case(case)

        assert seen["llm"] is not inner  # nodes talk to the recorder, not the raw adapter
        assert [call["purpose"] for call in result["llm_calls"]] == ["autofix"]
        assert result["terminal_state"] == "ready"


class TestBrowserLifecycle:
    @pytest.mark.asyncio
    async def test_browser_is_closed_even_when_the_graph_fails(self) -> None:
        browser = AsyncMock()
        services = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=browser,
        )
        case = MagicMock()
        case.repo_path = "/tmp/repo"
        case.case_id = "C-001"
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(side_effect=RuntimeError("graph exploded"))
        module = MagicMock()
        module.build_ddk_graph.return_value.compile.return_value = compiled

        with (
            patch("ddk.services.pipeline_runner.import_module", return_value=module),
            pytest.raises(RuntimeError, match="graph exploded"),
        ):
            await PipelineRunner(services).run_case(case)

        browser.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_screenshots_go_to_the_case_directory_and_thresholds_reach_the_validator(
        self, tmp_path
    ) -> None:
        services = RuntimeServices(
            llm=MagicMock(),
            filesystem=MagicMock(),
            git=MagicMock(),
            build_runner=MagicMock(),
            sandbox=MagicMock(),
            screenshot_diff=MagicMock(),
            browser=AsyncMock(),
            preview=MagicMock(),
            ssim_threshold=0.8,
            max_mismatch_ratio=0.1,
        )
        case = MagicMock()
        case.repo_path = str(tmp_path)
        case.case_id = "C-007"
        compiled = MagicMock()
        compiled.ainvoke = AsyncMock(return_value={})
        module = MagicMock()
        module.build_ddk_graph.return_value.compile.return_value = compiled

        with patch("ddk.services.pipeline_runner.import_module", return_value=module):
            await PipelineRunner(services).run_case(case, case_dir=tmp_path / "custom")

        container = compiled.ainvoke.call_args.kwargs["context"]
        validator = container.runtime_validator
        assert validator._visual_dir == tmp_path / "custom" / "artifacts" / "visual"
        assert (validator._ssim_threshold, validator._max_mismatch) == (0.8, 0.1)
        assert validator._preview is services.preview

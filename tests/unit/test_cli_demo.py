"""`ddk demo`: a key-less tour of the whole loop."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from ddk.cli import app
from ddk.demo.runner import DemoResult, FirstAttempt
from ddk.models.visual import VisualRegressionReport

runner = CliRunner()


def _result(workdir: Path, decision: str = "ready") -> DemoResult:
    final = VisualRegressionReport(
        case_id="C-001",
        reference_path="design.png",
        generated_path="page.png",
        ssim_score=0.999,
        pass_result=True,
    )
    return DemoResult(
        project_path=workdir / "project",
        design_path=workdir / "design.png",
        case_path=workdir / "project/.ddk/cases/C-001",
        summary={"release_decision": decision, "fix_attempts": 1, "scorecard_overall": 0.93},
        final_state={"visual_regression_report": final},
        first_attempt=FirstAttempt(
            ssim=0.888,
            mismatch_ratio=0.063,
            screenshot=workdir / "first-attempt/page.png",
            diff=workdir / "first-attempt/difference.png",
        ),
        report_path=workdir / "project/.ddk/cases/C-001/reports/report.html",
    )


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    started: list[Path] = []
    monkeypatch.setattr("ddk.cli.demo.real_services", lambda chromium_path: chromium_path)

    async def run_demo(workdir: Path, **kwargs: Any) -> DemoResult:
        started.append(workdir)
        kwargs["on_update"]("generate", {})
        return _result(workdir)

    monkeypatch.setattr("ddk.cli.demo.check_prerequisites", lambda **_: [])
    monkeypatch.setattr("ddk.cli.demo.run_demo", run_demo)
    return started


def test_demo_tells_the_story_and_names_the_files(tmp_path: Path, fake_run: list[Path]) -> None:
    result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")])

    assert result.exit_code == 0, result.output
    assert fake_run == [(tmp_path / "demo").resolve()]
    for expected in (
        "API 키 불필요",
        "코드 생성",
        "첫 시도",
        "SSIM 0.89",
        "6.3%",
        "자동 수정",
        "SSIM 1.00",
        "ready",
        "first-attempt/difference.png",
        "project/.ddk/cases/C-001/artifacts/visual/generated.png",
        "project/.ddk/cases/C-001/reports/report.html",
    ):
        assert expected in result.output


def test_demo_without_workdir_uses_a_fresh_temporary_folder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_run: list[Path]
) -> None:
    monkeypatch.setattr(
        "ddk.cli.demo.tempfile.mkdtemp", lambda prefix: str(tmp_path / f"{prefix}abc")
    )

    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 0, result.output
    assert fake_run == [tmp_path / "ddk-demo-abc"]


def test_missing_prerequisites_are_listed_and_nothing_runs(
    monkeypatch: pytest.MonkeyPatch, fake_run: list[Path]
) -> None:
    monkeypatch.setattr(
        "ddk.cli.demo.check_prerequisites", lambda **_: ["Node.js 와 npm 이 필요합니다."]
    )

    result = runner.invoke(app, ["demo"])

    assert result.exit_code == 1
    assert "Node.js" in result.output
    assert fake_run == []


def test_demo_that_does_not_end_ready_exits_with_an_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    async def run_demo(workdir: Path, **kwargs: Any) -> DemoResult:
        return _result(workdir, decision="blocked")

    monkeypatch.setattr("ddk.cli.demo.check_prerequisites", lambda **_: [])
    monkeypatch.setattr("ddk.cli.demo.run_demo", run_demo)

    result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")])

    assert result.exit_code == 1


def test_demo_reports_a_failure_to_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from ddk.demo.runner import DemoUnavailableError

    async def run_demo(workdir: Path, **kwargs: Any) -> DemoResult:
        raise DemoUnavailableError("npm ci failed: offline")

    monkeypatch.setattr("ddk.cli.demo.check_prerequisites", lambda **_: [])
    monkeypatch.setattr("ddk.cli.demo.run_demo", run_demo)

    result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")])

    assert result.exit_code == 1
    assert "npm ci failed: offline" in result.output


def test_chromium_path_from_the_environment_reaches_the_real_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    built: list[object] = []
    monkeypatch.setenv("DDK_CHROMIUM_PATH", "/x/chrome")
    monkeypatch.setattr("ddk.cli.demo.check_prerequisites", lambda **_: [])
    monkeypatch.setattr(
        "ddk.cli.demo.real_services", lambda chromium_path: built.append(chromium_path)
    )

    async def run_demo(workdir: Path, **kwargs: Any) -> DemoResult:
        return _result(workdir)

    monkeypatch.setattr("ddk.cli.demo.run_demo", run_demo)

    runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")])

    assert built == ["/x/chrome"]


class TestBrowserDownloadOffer:
    """With no Chromium, the first run offers the one-time download on a terminal."""

    @pytest.fixture
    def downloads(self, monkeypatch: pytest.MonkeyPatch, fake_run: list[Path]) -> list[str]:
        made: list[str] = []

        def check(install_browser: Callable[[], bool] | None = None) -> list[str]:
            assert install_browser is not None
            return [] if install_browser() else ["헤드리스 Chromium 을 사용할 수 없습니다"]

        def download() -> bool:
            made.append("download")
            return True

        monkeypatch.setattr("ddk.cli.demo.check_prerequisites", check)
        monkeypatch.setattr("ddk.cli.demo.install_chromium", download)
        return made

    def test_agreeing_downloads_it_and_the_demo_goes_on(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, downloads: list[str]
    ) -> None:
        monkeypatch.setattr("ddk.cli.demo.is_interactive", lambda: True)

        result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")], input="y\n")

        assert result.exit_code == 0, result.output
        assert downloads == ["download"]
        assert "내려받을까요" in result.output

    def test_pressing_enter_agrees(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, downloads: list[str]
    ) -> None:
        monkeypatch.setattr("ddk.cli.demo.is_interactive", lambda: True)

        runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")], input="\n")

        assert downloads == ["download"]

    def test_declining_downloads_nothing_and_the_problem_stays(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, downloads: list[str]
    ) -> None:
        monkeypatch.setattr("ddk.cli.demo.is_interactive", lambda: True)

        result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")], input="n\n")

        assert result.exit_code == 1
        assert downloads == []
        assert "Chromium" in result.output

    def test_nothing_is_asked_without_a_terminal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, downloads: list[str]
    ) -> None:
        monkeypatch.setattr("ddk.cli.demo.is_interactive", lambda: False)

        result = runner.invoke(app, ["demo", "--workdir", str(tmp_path / "demo")], input="y\n")

        assert result.exit_code == 1
        assert downloads == []
        assert "내려받을까요" not in result.output

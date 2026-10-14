"""AutoFixPlanner adjusts markup and styling from a failed visual comparison."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image

from ddk.models.generation import GeneratedArtifactSet, GeneratedFile
from ddk.models.validation import FailureRecord
from ddk.models.visual import MismatchRegion, VisualRegressionReport
from ddk.services.auto_fix_planner import AutoFixPlanner
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

APP = "export default function App() {\n  return <main className='page'><h1>Hi</h1></main>;\n}\n"
CSS = ".page { padding: 4px; color: #111; }\n"
UTIL = "export const add = (a: number, b: number) => a + b;\n"


def _artifacts(files: dict[str, str]) -> GeneratedArtifactSet:
    return GeneratedArtifactSet(
        case_id="C-001",
        files=[
            GeneratedFile(path=p, content=c, language="typescript", source_node_id="n")
            for p, c in files.items()
        ],
    )


def _visual_failure() -> FailureRecord:
    return FailureRecord(
        id="v1",
        taxonomy_id="FT-VISUAL-001",
        severity="major",
        message="Rendered page does not match the design: SSIM 0.71 (min 0.92)",
        source="visual",
        code="SSIM",
    )


def _lint_failure() -> FailureRecord:
    return FailureRecord(
        id="l1",
        taxonomy_id="FT-LINT-002",
        severity="minor",
        message="Missing semicolon",
        file_path="src/App.tsx",
        line_number=2,
        source="lint",
    )


def _report(tmp_path: Path, *, size: tuple[int, int] = (320, 200)) -> VisualRegressionReport:
    paths = {}
    for name, color in (
        ("reference", (255, 255, 255)),
        ("generated", (0, 0, 0)),
        ("diff", (255, 0, 0)),
    ):
        path = tmp_path / f"{name}.png"
        Image.new("RGB", size, color).save(path)
        paths[name] = path
    return VisualRegressionReport(
        case_id="C-001",
        reference_path=str(paths["reference"]),
        generated_path=str(paths["generated"]),
        diff_image_path=str(paths["diff"]),
        ssim_score=0.71,
        threshold=0.92,
        pass_result=False,
        mismatch_area_ratio=0.147,
        max_mismatch_ratio=0.03,
        mismatch_regions=[MismatchRegion(x=8, y=24, width=136, height=32, severity="high")],
        viewport="320x200",
    )


def _planner(llm: FakeLLMAdapter) -> AutoFixPlanner:
    return AutoFixPlanner(llm=llm, model="m")


def _images(call: dict[str, object]) -> list[tuple[str, str]]:
    messages = call["messages"]
    return [img for m in messages for img in (m.images or [])]  # type: ignore[attr-defined,union-attr]


class TestVisualRepair:
    async def test_model_sees_reference_current_page_and_diff(self, tmp_path: Path) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("Hi", "Hello")})
        artifacts = _artifacts({"src/App.tsx": APP})

        attempt, updated = await _planner(llm).plan_and_apply(
            [_visual_failure()], artifacts, "C-001", 1, visual=_report(tmp_path)
        )

        assert attempt.success and attempt.files_patched == ["src/App.tsx"]
        assert "Hello" in updated.files[0].content
        (call,) = llm.call_log
        pixels = []
        for data, media_type in _images(call):
            assert media_type == "image/png"
            with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                pixels.append(image.convert("RGB").getpixel((0, 0)))
        assert pixels == [(255, 255, 255), (0, 0, 0), (255, 0, 0)]

    async def test_prompt_states_scores_and_regions_and_uses_a_visual_purpose(
        self, tmp_path: Path
    ) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("Hi", "Hello")})

        await _planner(llm).plan_and_apply(
            [_visual_failure()], _artifacts({"src/App.tsx": APP}), "C-001", 1,
            visual=_report(tmp_path),
        )  # fmt: skip

        (call,) = llm.call_log
        user = call["messages"][-1].content
        assert "SSIM 0.71" in user and "14.7%" in user
        assert "x=8 y=24 136x32" in user
        assert call["config"].metadata["purpose"] == "autofix-visual"

    async def test_styles_and_main_component_are_adjusted_other_files_are_not(
        self, tmp_path: Path
    ) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "/* changed */\n"})
        artifacts = _artifacts({"src/util.ts": UTIL, "src/App.tsx": APP, "src/App.css": CSS})

        attempt, _ = await _planner(llm).plan_and_apply(
            [_visual_failure()], artifacts, "C-001", 1, visual=_report(tmp_path)
        )

        assert sorted(attempt.files_patched) == ["src/App.css", "src/App.tsx"]
        assert len(llm.call_log) == 2

    async def test_visual_failure_without_images_changes_nothing(self) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "unused"})

        attempt, _ = await _planner(llm).plan_and_apply(
            [_visual_failure()], _artifacts({"src/App.tsx": APP}), "C-001", 1, visual=None
        )

        assert not attempt.success
        assert llm.call_log == []

    async def test_project_without_ui_files_changes_nothing(self, tmp_path: Path) -> None:
        llm = FakeLLMAdapter(responses={"autofix": "unused"})

        attempt, _ = await _planner(llm).plan_and_apply(
            [_visual_failure()], _artifacts({"src/util.ts": UTIL}), "C-001", 1,
            visual=_report(tmp_path),
        )  # fmt: skip

        assert not attempt.success and llm.call_log == []

    async def test_code_failures_are_repaired_before_visual_ones(self, tmp_path: Path) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("</main>", ";</main>")})

        attempt, _ = await _planner(llm).plan_and_apply(
            [_lint_failure(), _visual_failure()], _artifacts({"src/App.tsx": APP}), "C-001", 1,
            visual=_report(tmp_path),
        )  # fmt: skip

        assert len(llm.call_log) == 1
        assert "Diagnostics for this file" in llm.call_log[0]["messages"][-1].content
        assert llm.call_log[0]["config"].metadata.get("purpose") != "autofix-visual"
        assert "v1" in attempt.remaining_failures

    async def test_large_images_are_downscaled_before_they_are_sent(self, tmp_path: Path) -> None:
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("Hi", "Hello")})

        await _planner(llm).plan_and_apply(
            [_visual_failure()], _artifacts({"src/App.tsx": APP}), "C-001", 1,
            visual=_report(tmp_path, size=(3000, 2000)),
        )  # fmt: skip

        (call,) = llm.call_log
        for data, _ in _images(call):
            with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                assert max(image.size) <= 1568

    async def test_unreadable_image_is_skipped_not_fatal(self, tmp_path: Path) -> None:
        report = _report(tmp_path)
        Path(report.diff_image_path or "").unlink()
        llm = FakeLLMAdapter(responses={"autofix": APP.replace("Hi", "Hello")})

        attempt, _ = await _planner(llm).plan_and_apply(
            [_visual_failure()], _artifacts({"src/App.tsx": APP}), "C-001", 1, visual=report
        )

        assert attempt.success
        assert len(_images(llm.call_log[0])) == 2

"""The evidence report: one HTML page that shows why a case got its verdict."""

from __future__ import annotations

import base64
import io
import re
from pathlib import Path

import pytest
from PIL import Image

from ddk.services.case_report import (
    ReportUnavailableError,
    load_case_report,
    render_html,
    write_report,
)
from tests.fakes.case_folder import make_case

PAYLOAD = '<script>alert("x")</script>'


@pytest.fixture(autouse=True)
def _english(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DDK_LANG", "en")


def _page(case: Path) -> str:
    return render_html(load_case_report(case))


def _embedded_images(page: str) -> list[Image.Image]:
    found = re.findall(r'src="data:image/(?:png|jpeg);base64,([^"]+)"', page)
    return [Image.open(io.BytesIO(base64.b64decode(blob))) for blob in found]


class TestLoading:
    def test_reads_the_verdict_scores_and_attempts(self, tmp_path: Path) -> None:
        report = load_case_report(make_case(tmp_path))

        assert report.case_id == "C-001"
        assert report.decision.decision == "ready"
        assert report.scorecard is not None and report.scorecard.grade == "A"
        assert [a.rule_id for a in report.attempts] == ["R-10"]
        assert [r.number for r in report.rounds] == [1, 2]
        assert [r.visual.ssim_score for r in report.rounds] == [0.88, 0.99]

    def test_rounds_are_ordered_by_number_not_by_name(self, tmp_path: Path) -> None:
        case = make_case(tmp_path, ssims=(0.5,) * 10 + (0.99,))

        numbers = [r.number for r in load_case_report(case).rounds]

        assert numbers == list(range(1, 12))

    def test_images_come_from_the_case_folder_not_from_recorded_paths(self, tmp_path: Path) -> None:
        report = load_case_report(make_case(tmp_path))

        assert report.design is not None and report.design.is_file()
        for round_ in report.rounds:
            assert round_.screenshot is not None and round_.screenshot.is_file()
            assert round_.difference is not None and round_.difference.is_file()

    def test_a_case_from_before_rounds_were_kept_shows_its_one_comparison(
        self, tmp_path: Path
    ) -> None:
        case = make_case(tmp_path, ssims=(0.99,))
        visual = case / "artifacts" / "visual"
        (visual / "generated.png").write_bytes((visual / "round-1" / "generated.png").read_bytes())
        (visual / "diff.png").write_bytes((visual / "round-1" / "diff.png").read_bytes())
        (case / "reports" / "visual-regression-report.json").write_text(
            (visual / "round-1" / "report.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
        for leftover in (visual / "round-1").iterdir():
            leftover.unlink()
        (visual / "round-1").rmdir()

        report = load_case_report(case)

        assert [r.number for r in report.rounds] == [1]
        assert report.rounds[0].screenshot == visual / "generated.png"

    def test_a_folder_without_a_verdict_is_not_a_report(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)
        (case / "reports" / "release-decision.json").unlink()

        with pytest.raises(ReportUnavailableError, match="release-decision.json"):
            load_case_report(case)

    def test_a_folder_that_does_not_exist_is_not_a_report(self, tmp_path: Path) -> None:
        with pytest.raises(ReportUnavailableError):
            load_case_report(tmp_path / "nope")

    def test_everything_but_the_verdict_may_be_missing(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)
        for name in (
            "scorecard.json",
            "evidence-pack.json",
            "fix-attempts.json",
            "runtime-validation-report.json",
            "generated-artifacts.json",
            "llm-calls.json",
            "case-input.json",
        ):
            (case / "reports" / name).unlink()
        for folder in (case / "artifacts").iterdir():
            for item in sorted(folder.rglob("*"), reverse=True):
                item.unlink() if item.is_file() else item.rmdir()

        page = _page(case)

        assert "ready" in page.lower()
        assert "<img" not in page


class TestPage:
    def test_it_is_one_self_contained_document(self, tmp_path: Path) -> None:
        page = _page(make_case(tmp_path))

        assert page.startswith("<!doctype html>")
        assert '<html lang="en">' in page
        assert "<title>" in page and "C-001" in page
        # nothing is fetched from anywhere
        assert not re.search(r'(?:src|href)="(?:https?:)?//', page)
        assert "<link" not in page

    def test_it_states_the_verdict_the_score_and_the_numbers_behind_it(
        self, tmp_path: Path
    ) -> None:
        page = _page(make_case(tmp_path))

        for expected in (
            "Ready to apply",
            "0.96",
            "SSIM 0.88",
            "SSIM 0.99",
            "6.3%",
            "R-10",
            "src/App.tsx",
            "claude-sonnet-5-5",
            "$0.0123",
            "Build the dashboard shown in the design",
        ):
            assert expected in page, expected

    def test_every_round_shows_its_own_pictures(self, tmp_path: Path) -> None:
        page = _page(make_case(tmp_path))

        # design + (result, difference) x 2 rounds, and the design again in the overlay
        assert len(_embedded_images(page)) == 1 + 2 * 2 + 2

    def test_a_blocked_case_lists_what_blocks_it(self, tmp_path: Path) -> None:
        page = _page(make_case(tmp_path, decision="blocked", ssims=(0.88,)))

        assert "Blocked" in page
        assert "visual-mismatch" in page
        assert "FT-VISUAL-001" in page
        assert "SSIM 0.88 is below 0.92" in page

    def test_text_from_the_run_cannot_inject_markup(self, tmp_path: Path) -> None:
        case = make_case(
            tmp_path,
            decision="blocked",
            attempt_note=PAYLOAD,
            failure_message=PAYLOAD,
            file_path="src/<b>x</b>.tsx",
        )

        page = _page(case)

        assert PAYLOAD not in page
        assert "<b>x</b>" not in page
        assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in page
        assert page.count("<script") == 1  # the overlay script, nothing else

    def test_missing_pictures_leave_a_note_instead_of_a_broken_image(self, tmp_path: Path) -> None:
        page = _page(make_case(tmp_path, with_images=False))

        assert "<img" not in page
        assert "Image not available" in page

    def test_large_pictures_are_shrunk(self, tmp_path: Path) -> None:
        page = _page(make_case(tmp_path, design_size=(3000, 2000)))

        images = _embedded_images(page)
        assert images and max(image.width for image in images) <= 1100
        assert len(page) < 2_000_000

    def test_the_overlay_needs_both_pictures(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)
        (case / "artifacts" / "inputs" / "design.png").unlink()

        assert '<div class="compare"' not in _page(case)

    def test_the_page_follows_the_language(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        case = make_case(tmp_path)
        monkeypatch.setenv("DDK_LANG", "ko")

        page = _page(case)

        assert '<html lang="ko">' in page
        assert "적용 가능" in page
        assert "Ready to apply" not in page


class TestWrite:
    def test_default_place_is_the_reports_folder(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)

        out = write_report(case)

        assert out == case / "reports" / "report.html"
        assert out.read_text(encoding="utf-8").startswith("<!doctype html>")

    def test_another_place_can_be_chosen(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)
        target = tmp_path / "out" / "nested" / "page.html"

        assert write_report(case, target) == target
        assert target.is_file()

    def test_nothing_is_written_when_there_is_no_verdict(self, tmp_path: Path) -> None:
        case = make_case(tmp_path)
        (case / "reports" / "release-decision.json").unlink()

        with pytest.raises(ReportUnavailableError):
            write_report(case)

        assert not (case / "reports" / "report.html").exists()

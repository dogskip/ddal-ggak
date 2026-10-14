"""Tests for models/visual.py — MismatchRegion, VisualRegressionReport."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from ddk.models.visual import MismatchRegion, VisualRegressionReport


class TestMismatchRegion:
    def test_create(self) -> None:
        region = MismatchRegion(x=10, y=20, width=100, height=50, severity="high")
        assert region.x == 10
        assert region.severity == "high"

    def test_severity_restricted(self) -> None:
        with pytest.raises(ValidationError):
            MismatchRegion(x=0, y=0, width=1, height=1, severity="extreme")  # type: ignore[arg-type]


class TestVisualRegressionReport:
    def test_create_passing(self) -> None:
        report = VisualRegressionReport(
            case_id="case-1",
            reference_path="/ref.png",
            generated_path="/gen.png",
            ssim_score=0.95,
            pass_result=True,
        )
        assert report.threshold == 0.92
        assert report.mismatch_regions == []
        assert report.diff_image_path is None
        assert isinstance(report.created_at, datetime)

    def test_create_failing(self) -> None:
        region = MismatchRegion(x=0, y=0, width=50, height=50, severity="medium")
        report = VisualRegressionReport(
            case_id="case-2",
            reference_path="/ref.png",
            generated_path="/gen.png",
            ssim_score=0.5,
            pass_result=False,
            mismatch_regions=[region],
            diff_image_path="/diff.png",
        )
        assert len(report.mismatch_regions) == 1
        assert report.diff_image_path == "/diff.png"

    def test_ssim_score_lower_bound(self) -> None:
        with pytest.raises(ValidationError):
            VisualRegressionReport(
                case_id="c",
                reference_path="r",
                generated_path="g",
                ssim_score=-0.1,
                pass_result=False,
            )

    def test_ssim_score_upper_bound(self) -> None:
        with pytest.raises(ValidationError):
            VisualRegressionReport(
                case_id="c",
                reference_path="r",
                generated_path="g",
                ssim_score=1.1,
                pass_result=False,
            )

    def test_threshold_bounds(self) -> None:
        with pytest.raises(ValidationError):
            VisualRegressionReport(
                case_id="c",
                reference_path="r",
                generated_path="g",
                ssim_score=0.5,
                threshold=1.5,
                pass_result=False,
            )

    def test_serialization_roundtrip(self) -> None:
        report = VisualRegressionReport(
            case_id="c-rt",
            reference_path="r",
            generated_path="g",
            ssim_score=0.99,
            pass_result=True,
        )
        data = report.model_dump()
        restored = VisualRegressionReport.model_validate(data)
        assert restored.case_id == "c-rt"
        assert restored.ssim_score == 0.99

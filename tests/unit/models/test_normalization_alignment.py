"""TDD tests for NormalizationReport + ConventionFix design-spec alignment (03-00)."""

from __future__ import annotations

import pytest

from ddk.models.normalization import ConventionFix, NormalizationReport


def _make_fix(severity: str = "must-fix", fix_type: str = "naming") -> ConventionFix:
    """Helper to create a ConventionFix with required existing fields."""
    return ConventionFix(
        file_path="src/App.tsx",
        rule_id="R1",
        description="test fix",
        before_snippet="old",
        after_snippet="new",
        severity=severity,  # type: ignore[arg-type]
        fix_type=fix_type,  # type: ignore[arg-type]
    )


class TestConventionFixDesignSpecFields:
    """ConventionFix must have fix_type, severity, before, after per 12-data-models.md §5."""

    def test_fix_type_default_naming(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="b", after_snippet="a"
        )
        assert fix.fix_type == "naming"

    def test_severity_default_must_fix(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="b", after_snippet="a"
        )
        assert fix.severity == "must-fix"

    def test_before_default_none(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="b", after_snippet="a"
        )
        assert fix.before is None

    def test_after_default_none(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="b", after_snippet="a"
        )
        assert fix.after is None

    def test_fix_type_all_valid_literals(self) -> None:
        valid_types = [
            "naming", "import_order", "file_placement", "token_replace",
            "primitive_reuse", "helper_dedup", "type_annotation"
        ]
        for ft in valid_types:
            fix = ConventionFix(
                file_path="x", rule_id="R1", description="d",
                before_snippet="b", after_snippet="a", fix_type=ft  # type: ignore
            )
            assert fix.fix_type == ft

    def test_severity_all_valid_literals(self) -> None:
        for sev in ["must-fix", "should-fix", "nice-to-have"]:
            fix = ConventionFix(
                file_path="x", rule_id="R1", description="d",
                before_snippet="b", after_snippet="a", severity=sev  # type: ignore
            )
            assert fix.severity == sev

    def test_before_after_can_be_set(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="old", after_snippet="new",
            before="const a = 1", after="const A = 1",
        )
        assert fix.before == "const a = 1"
        assert fix.after == "const A = 1"

    def test_existing_fields_still_present(self) -> None:
        fix = ConventionFix(
            file_path="src/App.tsx", rule_id="NAMING-001",
            description="Rename", before_snippet="old", after_snippet="new"
        )
        assert fix.file_path == "src/App.tsx"
        assert fix.rule_id == "NAMING-001"
        assert fix.description == "Rename"
        assert fix.before_snippet == "old"
        assert fix.after_snippet == "new"

    def test_roundtrip_with_new_fields(self) -> None:
        fix = ConventionFix(
            file_path="x", rule_id="R1", description="d",
            before_snippet="b", after_snippet="a",
            fix_type="import_order", severity="should-fix",
            before="import B", after="import A",
        )
        data = fix.model_dump()
        restored = ConventionFix.model_validate(data)
        assert restored == fix
        assert restored.fix_type == "import_order"
        assert restored.severity == "should-fix"


class TestNormalizationReportDesignSpecFields:
    """NormalizationReport must have convention_fixes, drift scores, unresolved_drift per spec."""

    def test_convention_fixes_default_empty(self) -> None:
        report = NormalizationReport(case_id="c")
        assert report.convention_fixes == []

    def test_drift_score_before_default_zero(self) -> None:
        report = NormalizationReport(case_id="c")
        assert report.drift_score_before == 0.0

    def test_drift_score_after_default_zero(self) -> None:
        report = NormalizationReport(case_id="c")
        assert report.drift_score_after == 0.0

    def test_unresolved_drift_default_empty(self) -> None:
        report = NormalizationReport(case_id="c")
        assert report.unresolved_drift == []

    def test_drift_score_bounds_ge_0(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NormalizationReport(case_id="c", drift_score_before=-0.1)

    def test_drift_score_bounds_le_10(self) -> None:
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            NormalizationReport(case_id="c", drift_score_after=10.1)

    def test_existing_fields_still_present(self) -> None:
        fix = ConventionFix(
            file_path="a.tsx", rule_id="R1", description="fix",
            before_snippet="b", after_snippet="a"
        )
        report = NormalizationReport(
            case_id="c",
            fixes=[fix],
            files_modified=["a.tsx"],
            skipped_rules=["R2"],
            duration_ms=100,
        )
        assert len(report.fixes) == 1
        assert report.files_modified == ["a.tsx"]
        assert report.skipped_rules == ["R2"]
        assert report.duration_ms == 100

    def test_no_mutable_default_sharing_convention_fixes(self) -> None:
        r1 = NormalizationReport(case_id="c1")
        r2 = NormalizationReport(case_id="c2")
        r1.convention_fixes.append(_make_fix())
        assert r2.convention_fixes == [], "Mutable default shared — use Field(default_factory=list)"


class TestComputeDriftScore:
    """NormalizationReport.compute_drift_score() static method per 12-data-models.md §5."""

    def test_empty_fixes_returns_zero(self) -> None:
        assert NormalizationReport.compute_drift_score([]) == 0.0

    def test_single_must_fix_returns_2(self) -> None:
        assert NormalizationReport.compute_drift_score([_make_fix("must-fix")]) == 2.0

    def test_single_should_fix_returns_1(self) -> None:
        assert NormalizationReport.compute_drift_score([_make_fix("should-fix")]) == 1.0

    def test_single_nice_to_have_returns_0_5(self) -> None:
        assert NormalizationReport.compute_drift_score([_make_fix("nice-to-have")]) == 0.5

    def test_mixed_severities_summed(self) -> None:
        fixes = [_make_fix("must-fix"), _make_fix("should-fix"), _make_fix("nice-to-have")]
        # 2.0 + 1.0 + 0.5 = 3.5
        assert NormalizationReport.compute_drift_score(fixes) == 3.5

    def test_capped_at_10(self) -> None:
        # 6 must-fix = 12.0 raw, capped at 10.0
        fixes = [_make_fix("must-fix") for _ in range(6)]
        assert NormalizationReport.compute_drift_score(fixes) == 10.0

    def test_exactly_at_cap(self) -> None:
        # 5 must-fix = 10.0 raw, exactly at cap
        fixes = [_make_fix("must-fix") for _ in range(5)]
        assert NormalizationReport.compute_drift_score(fixes) == 10.0

    def test_just_below_cap(self) -> None:
        # 4 must-fix + 1 should-fix = 9.0, not capped
        fixes = [_make_fix("must-fix")] * 4 + [_make_fix("should-fix")]
        assert NormalizationReport.compute_drift_score(fixes) == 9.0

    def test_is_static_method(self) -> None:
        """Can be called on class, not instance."""
        score = NormalizationReport.compute_drift_score([])
        assert isinstance(score, float)

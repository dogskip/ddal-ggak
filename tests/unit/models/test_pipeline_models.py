"""Tests for pipeline models: generation, normalization, validation, visual, fix."""

from __future__ import annotations

from ddk.models.fix import FixAttempt
from ddk.models.generation import (
    GeneratedArtifactSet,
    GeneratedFile,
    GenerationNode,
    GenerationPlan,
)
from ddk.models.normalization import ConventionFix, NormalizationReport
from ddk.models.validation import (
    FAILURE_TAXONOMY,
    FailureRecord,
    RuntimeValidationReport,
)
from ddk.models.visual import MismatchRegion, VisualRegressionReport


class TestGenerationNode:
    def test_generation_node_roundtrip(self) -> None:
        node = GenerationNode(
            id="node-1",
            node_type="component",
            target_path="src/components/Header.tsx",
            dependencies=["node-0"],
            validation_hooks=["validate_header"],
            repair_hooks=["repair_header"],
        )
        data = node.model_dump()
        restored = GenerationNode.model_validate(data)
        assert restored == node
        assert restored.id == "node-1"
        assert restored.node_type == "component"
        assert restored.target_path == "src/components/Header.tsx"
        assert restored.dependencies == ["node-0"]

    def test_generation_node_defaults(self) -> None:
        node = GenerationNode(id="n1", node_type="component", target_path="src/A.tsx")
        assert node.dependencies == []
        assert node.validation_hooks == []
        assert node.repair_hooks == []
        assert node.generation_prompt_hint is None


class TestGenerationPlan:
    def test_generation_plan_roundtrip(self) -> None:
        nodes = [
            GenerationNode(id="n1", node_type="component", target_path="src/A.tsx"),
            GenerationNode(
                id="n2",
                node_type="style",
                target_path="src/A.module.css",
                dependencies=["n1"],
            ),
        ]
        plan = GenerationPlan(
            case_id="case-001",
            nodes=nodes,
            execution_order=["n1", "n2"],
            target_files=["src/A.tsx", "src/A.module.css"],
            estimated_node_count=2,
        )
        data = plan.model_dump()
        restored = GenerationPlan.model_validate(data)
        assert len(restored.nodes) == 2
        assert restored.execution_order == ["n1", "n2"]
        assert restored.target_files == ["src/A.tsx", "src/A.module.css"]
        assert restored.estimated_node_count == 2

    def test_generation_plan_json_roundtrip(self) -> None:
        plan = GenerationPlan(
            case_id="c1",
            nodes=[GenerationNode(id="n1", node_type="component", target_path="src/X.tsx")],
            execution_order=["n1"],
            target_files=["src/X.tsx"],
            estimated_node_count=1,
        )
        json_str = plan.model_dump_json()
        restored = GenerationPlan.model_validate_json(json_str)
        assert restored == plan


class TestGeneratedFile:
    def test_generated_file_roundtrip(self) -> None:
        gf = GeneratedFile(
            path="src/App.tsx",
            content="export default function App() {}",
            language="typescript",
            source_node_id="n1",
        )
        data = gf.model_dump()
        restored = GeneratedFile.model_validate(data)
        assert restored == gf
        assert restored.language == "typescript"

    def test_generated_file_default_language(self) -> None:
        gf = GeneratedFile(path="f.tsx", content="code", source_node_id="n1")
        assert gf.language == "typescript"


class TestGeneratedArtifactSet:
    def test_generated_artifact_set_roundtrip(self) -> None:
        files = [
            GeneratedFile(path="a.tsx", content="c1", source_node_id="n1"),
            GeneratedFile(path="b.css", content="c2", language="css", source_node_id="n1"),
        ]
        art = GeneratedArtifactSet(
            case_id="case-001",
            files=files,
            file_map={"a.tsx": "n1", "b.css": "n1"},
            generation_trace=["step1", "step2"],
            total_tokens_used=1000,
        )
        data = art.model_dump()
        restored = GeneratedArtifactSet.model_validate(data)
        assert restored.case_id == art.case_id
        assert len(restored.files) == 2
        assert restored.file_map == {"a.tsx": "n1", "b.css": "n1"}


class TestConventionFix:
    def test_convention_fix_roundtrip(self) -> None:
        fix = ConventionFix(
            file_path="src/App.tsx",
            rule_id="NAMING-001",
            description="Rename to PascalCase",
            before_snippet="const app = ...",
            after_snippet="const App = ...",
        )
        data = fix.model_dump()
        restored = ConventionFix.model_validate(data)
        assert restored == fix


class TestNormalizationReport:
    def test_normalization_report_roundtrip(self) -> None:
        report = NormalizationReport(
            case_id="case-001",
            fixes=[
                ConventionFix(
                    file_path="a.tsx",
                    rule_id="R1",
                    description="fix",
                    before_snippet="b",
                    after_snippet="a",
                ),
            ],
            files_modified=["a.tsx"],
            skipped_rules=["R2"],
            duration_ms=150,
        )
        data = report.model_dump()
        restored = NormalizationReport.model_validate(data)
        assert restored.case_id == "case-001"
        assert len(restored.fixes) == 1
        assert restored.duration_ms == 150


class TestFailureTaxonomy:
    def test_failure_taxonomy_exists(self) -> None:
        assert isinstance(FAILURE_TAXONOMY, dict)
        assert len(FAILURE_TAXONOMY) > 0
        # All keys should be string IDs
        for key in FAILURE_TAXONOMY:
            assert isinstance(key, str)
            assert isinstance(FAILURE_TAXONOMY[key], str)


class TestFailureRecord:
    def test_failure_record_roundtrip(self) -> None:
        fr = FailureRecord(
            id="fail-001",
            taxonomy_id="FT-BUILD-001",
            severity="critical",
            message="Build failed",
            file_path="src/App.tsx",
            line_number=42,
            raw_output="Error: cannot find module",
            suggested_fix="Install missing dependency",
        )
        data = fr.model_dump()
        restored = FailureRecord.model_validate(data)
        assert restored == fr
        assert restored.severity == "critical"


class TestRuntimeValidationReport:
    def test_runtime_validation_report_roundtrip(self) -> None:
        failures = [
            FailureRecord(
                id="f1",
                taxonomy_id="FT-BUILD-001",
                severity="major",
                message="type error",
                raw_output="err",
            ),
        ]
        report = RuntimeValidationReport(
            case_id="case-001",
            build_success=False,
            type_check_success=False,
            lint_success=True,
            runtime_errors=["Error at line 10"],
            failures=failures,
            duration_ms=3000,
        )
        data = report.model_dump()
        restored = RuntimeValidationReport.model_validate(data)
        assert restored.case_id == "case-001"
        assert restored.build_success is False
        assert len(restored.failures) == 1
        assert restored.duration_ms == 3000


class TestMismatchRegion:
    def test_mismatch_region_roundtrip(self) -> None:
        region = MismatchRegion(
            x=10, y=20, width=100, height=50, severity="high",
        )
        data = region.model_dump()
        restored = MismatchRegion.model_validate(data)
        assert restored == region
        assert restored.severity == "high"


class TestVisualRegressionReport:
    def test_visual_regression_report_roundtrip(self) -> None:
        regions = [
            MismatchRegion(x=0, y=0, width=50, height=50, severity="medium"),
        ]
        report = VisualRegressionReport(
            case_id="case-001",
            reference_path="/ref/screenshot.png",
            generated_path="/gen/screenshot.png",
            ssim_score=0.85,
            threshold=0.92,
            pass_result=False,
            mismatch_regions=regions,
            diff_image_path="/diff/screenshot.png",
        )
        data = report.model_dump()
        restored = VisualRegressionReport.model_validate(data)
        assert restored.case_id == "case-001"
        assert restored.ssim_score == 0.85
        assert restored.pass_result is False
        assert len(restored.mismatch_regions) == 1


class TestFixAttempt:
    def test_fix_attempt_roundtrip(self) -> None:
        attempt = FixAttempt(
            attempt_number=1,
            case_id="case-001",
            trigger_failures=["FT-BUILD-001"],
            rule_id="RULE-001",
            files_patched=["src/App.tsx"],
            patch_description="Fixed missing import",
            success=True,
            remaining_failures=[],
            checkpoint_ref="chk-abc",
            duration_ms=500,
        )
        data = attempt.model_dump()
        restored = FixAttempt.model_validate(data)
        assert restored == attempt
        assert restored.attempt_number == 1
        assert restored.success is True

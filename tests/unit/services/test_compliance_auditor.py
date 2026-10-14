"""Unit tests for the Standards Compliance Auditor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddk.services.compliance_auditor import CatalogLoadError, ComplianceAuditor


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root not found")


def _write_catalog(root: Path, clauses: list[dict]) -> None:
    (root / "benchmarks").mkdir(parents=True, exist_ok=True)
    (root / "benchmarks" / "standards-catalog.json").write_text(
        json.dumps({"clauses": clauses}), encoding="utf-8"
    )


def _clause(standard: str, artifacts: list[dict]) -> dict:
    return {
        "standard": standard,
        "clause": "c",
        "title": "t",
        "requirement": "r",
        "artifacts": artifacts,
    }


def _touch(root: Path, relpath: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")


class TestCatalogLoading:
    def test_missing_catalog_raises(self, tmp_path: Path) -> None:
        with pytest.raises(CatalogLoadError):
            ComplianceAuditor(tmp_path).load_catalog()

    def test_bad_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "benchmarks").mkdir()
        (tmp_path / "benchmarks" / "standards-catalog.json").write_text("{bad")
        with pytest.raises(CatalogLoadError):
            ComplianceAuditor(tmp_path).load_catalog()

    def test_missing_clauses_key_raises(self, tmp_path: Path) -> None:
        (tmp_path / "benchmarks").mkdir()
        (tmp_path / "benchmarks" / "standards-catalog.json").write_text("{}")
        with pytest.raises(CatalogLoadError):
            ComplianceAuditor(tmp_path).load_catalog()


class TestAuditResolution:
    def test_mapped_when_all_artifacts_exist(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, [_clause("S", [{"kind": "doc", "path": "d/a.md"}])])
        _touch(tmp_path, "d/a.md")
        report = ComplianceAuditor(tmp_path).audit()
        assert report.clauses[0].status == "mapped"
        assert report.coverage == 1.0

    def test_gap_when_artifact_missing(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, [_clause("S", [{"kind": "doc", "path": "d/missing.md"}])])
        report = ComplianceAuditor(tmp_path).audit()
        assert report.clauses[0].status == "gap"
        assert report.gaps == 1

    def test_partial_when_mixed(self, tmp_path: Path) -> None:
        _write_catalog(
            tmp_path,
            [
                _clause(
                    "S",
                    [{"kind": "doc", "path": "d/a.md"}, {"kind": "doc", "path": "d/b.md"}],
                )
            ],
        )
        _touch(tmp_path, "d/a.md")
        report = ComplianceAuditor(tmp_path).audit()
        assert report.clauses[0].status == "partial"

    def test_per_standard_rollup(self, tmp_path: Path) -> None:
        _write_catalog(
            tmp_path,
            [
                _clause("A", [{"kind": "doc", "path": "a.md"}]),
                _clause("A", [{"kind": "doc", "path": "missing.md"}]),
                _clause("B", [{"kind": "doc", "path": "b.md"}]),
            ],
        )
        _touch(tmp_path, "a.md")
        _touch(tmp_path, "b.md")
        auditor = ComplianceAuditor(tmp_path)
        rollup = auditor.per_standard(auditor.audit())
        assert rollup["A"] == {"total": 2, "mapped": 1, "partial": 0, "gap": 1}
        assert rollup["B"]["mapped"] == 1


class TestWriteMatrix:
    def test_writes_valid_json(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, [_clause("S", [{"kind": "doc", "path": "a.md"}])])
        _touch(tmp_path, "a.md")
        auditor = ComplianceAuditor(tmp_path)
        out = auditor.write_matrix(auditor.audit())
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["clauses"][0]["status"] == "mapped"
        assert "coverage" in data


class TestRealCatalog:
    """The shipped catalog must audit honestly against the live repo."""

    def test_real_catalog_has_coverage_and_honest_gaps(self) -> None:
        report = ComplianceAuditor(_repo_root()).audit()
        assert report.total >= 14
        assert report.mapped >= 10
        # Honesty: the catalog includes artifacts the project genuinely lacks.
        assert report.gaps >= 1, "catalog must surface real gaps, not rubber-stamp"
        assert 0.0 < report.coverage < 1.0
        assert "ISO/IEC 25010:2023" in report.standards

    def test_compatibility_clause_is_a_real_gap(self) -> None:
        report = ComplianceAuditor(_repo_root()).audit()
        compat = [c for c in report.clauses if c.clause == "Compatibility"]
        assert compat and compat[0].status == "gap"

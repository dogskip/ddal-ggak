"""Unit tests for the Proof Program — ProofLedger + ClaimGate.

The decisive tests here are the *anti-overclaim* guarantees: superiority is
denied unless a calibrated baseline and a comparative artifact exist, and
superset is denied if any inherit/elevate family lacks resolved evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddk.services.proof_ledger import ClaimGate, MatrixLoadError, ProofLedger


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise RuntimeError("repo root not found")


def _write_matrix(root: Path, families: list[dict]) -> None:
    (root / "benchmarks").mkdir(parents=True, exist_ok=True)
    (root / "benchmarks" / "capability-matrix.json").write_text(
        json.dumps({"families": families}), encoding="utf-8"
    )


def _fam(fam_id: str, classification: str, evidence: list[dict]) -> dict:
    return {
        "id": fam_id,
        "name": fam_id,
        "gsd_baseline": "x",
        "ddk_target": "y",
        "classification": classification,
        "evidence": evidence,
    }


def _touch(root: Path, relpath: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("ok", encoding="utf-8")


def _identity_docs(root: Path) -> None:
    _touch(root, "docs/design/27-identity-positioning.md")
    _touch(root, "docs/design/02-prd.md")


def _claim(report, claim_type: str, subject: str = ""):  # noqa: ANN001
    for c in report.claims:
        if c.claim_type == claim_type and c.subject == subject:
            return c
    raise AssertionError(f"claim not found: {claim_type}/{subject}")


class TestMatrixLoading:
    def test_missing_matrix_raises(self, tmp_path: Path) -> None:
        with pytest.raises(MatrixLoadError):
            ProofLedger(tmp_path).load_matrix()

    def test_bad_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "benchmarks").mkdir()
        (tmp_path / "benchmarks" / "capability-matrix.json").write_text("{not json")
        with pytest.raises(MatrixLoadError):
            ProofLedger(tmp_path).load_matrix()

    def test_missing_families_key_raises(self, tmp_path: Path) -> None:
        _touch(tmp_path, "benchmarks/capability-matrix.json")
        (tmp_path / "benchmarks" / "capability-matrix.json").write_text("{}")
        with pytest.raises(MatrixLoadError):
            ProofLedger(tmp_path).load_matrix()


class TestEvidenceResolution:
    def test_present_evidence_marks_mapped(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_fam("f", "elevate", [{"kind": "code", "path": "src/f.py"}])])
        _touch(tmp_path, "src/f.py")
        report = ProofLedger(tmp_path).verify()
        assert report.families[0].state == "mapped"

    def test_missing_evidence_marks_pending(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_fam("f", "elevate", [{"kind": "code", "path": "src/f.py"}])])
        report = ProofLedger(tmp_path).verify()
        assert report.families[0].state == "pending"

    def test_mixed_evidence_marks_partial(self, tmp_path: Path) -> None:
        _write_matrix(
            tmp_path,
            [
                _fam(
                    "f",
                    "new",
                    [
                        {"kind": "code", "path": "src/f.py"},
                        {"kind": "code", "path": "src/g.py"},
                    ],
                )
            ],
        )
        _touch(tmp_path, "src/f.py")
        report = ProofLedger(tmp_path).verify()
        assert report.families[0].state == "partial"

    def test_evidence_path_cannot_escape_repository(self, tmp_path: Path) -> None:
        outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
        outside.write_text("not repository evidence", encoding="utf-8")
        _write_matrix(
            tmp_path,
            [_fam("f", "elevate", [{"kind": "code", "path": f"../{outside.name}"}])],
        )

        report = ProofLedger(tmp_path).verify()

        assert report.families[0].evidence[0].exists is False
        assert report.families[0].evidence[0].resolution_error is not None
        assert _claim(report, "parity", "f").allowed is False


class TestIdentityGate:
    def test_allowed_when_both_docs_present(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [])
        _identity_docs(tmp_path)
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "identity").allowed is True

    def test_denied_when_prd_missing(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [])
        _touch(tmp_path, "docs/design/27-identity-positioning.md")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "identity").allowed is False


class TestParityGate:
    def test_artifact_mapping_alone_does_not_allow_parity(self, tmp_path: Path) -> None:
        _write_matrix(
            tmp_path,
            [
                _fam("good", "elevate", [{"kind": "code", "path": "src/a.py"}]),
                _fam("bad", "elevate", [{"kind": "code", "path": "src/missing.py"}]),
            ],
        )
        _touch(tmp_path, "src/a.py")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "parity", "good").allowed is False
        assert "behavior verification receipt missing" in _claim(report, "parity", "good").unmet
        assert _claim(report, "parity", "bad").allowed is False


class TestSupersetGate:
    def test_denied_when_all_artifacts_mapped_but_behavior_unproved(self, tmp_path: Path) -> None:
        _write_matrix(
            tmp_path,
            [
                _fam("i", "inherit", [{"kind": "code", "path": "src/i.py"}]),
                _fam("e", "elevate", [{"kind": "code", "path": "src/e.py"}]),
                _fam("n", "new", [{"kind": "code", "path": "src/n_missing.py"}]),
            ],
        )
        _identity_docs(tmp_path)
        _touch(tmp_path, "src/i.py")
        _touch(tmp_path, "src/e.py")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superset").allowed is False

    def test_denied_when_mapped_family_unproved(self, tmp_path: Path) -> None:
        _write_matrix(
            tmp_path,
            [
                _fam("i", "inherit", [{"kind": "code", "path": "src/i.py"}]),
                _fam("e", "elevate", [{"kind": "code", "path": "src/e_missing.py"}]),
            ],
        )
        _identity_docs(tmp_path)
        _touch(tmp_path, "src/i.py")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superset").allowed is False

    def test_denied_when_identity_missing(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_fam("i", "inherit", [{"kind": "code", "path": "src/i.py"}])])
        _touch(tmp_path, "src/i.py")  # proved, but no identity docs
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superset").allowed is False


class TestSuperiorityGate:
    """The anti-overclaim guarantee."""

    def _proved_repo(self, root: Path) -> None:
        _write_matrix(root, [_fam("e", "elevate", [{"kind": "code", "path": "src/e.py"}])])
        _identity_docs(root)
        _touch(root, "src/e.py")

    def test_denied_when_baseline_missing(self, tmp_path: Path) -> None:
        self._proved_repo(tmp_path)
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superiority").allowed is False

    def test_denied_when_baseline_uncalibrated(self, tmp_path: Path) -> None:
        self._proved_repo(tmp_path)
        (tmp_path / "benchmarks" / "gsd-baseline.json").write_text(
            json.dumps({"calibrated": False})
        )
        _touch(tmp_path, "benchmarks/comparative-scorecard.json")
        report = ProofLedger(tmp_path).verify()
        # Even with comparative artifact + parity, uncalibrated baseline → DENIED.
        assert _claim(report, "superiority").allowed is False

    def test_denied_when_comparative_missing(self, tmp_path: Path) -> None:
        self._proved_repo(tmp_path)
        (tmp_path / "benchmarks" / "gsd-baseline.json").write_text(json.dumps({"calibrated": True}))
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superiority").allowed is False

    def test_denied_without_behavior_proof_even_with_comparative_artifacts(
        self, tmp_path: Path
    ) -> None:
        self._proved_repo(tmp_path)
        (tmp_path / "benchmarks" / "gsd-baseline.json").write_text(json.dumps({"calibrated": True}))
        _touch(tmp_path, "benchmarks/comparative-scorecard.json")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superiority").allowed is False
        assert report.maturity_level == "P-3"

    def test_malformed_baseline_treated_uncalibrated(self, tmp_path: Path) -> None:
        self._proved_repo(tmp_path)
        (tmp_path / "benchmarks" / "gsd-baseline.json").write_text("{broken")
        _touch(tmp_path, "benchmarks/comparative-scorecard.json")
        report = ProofLedger(tmp_path).verify()
        assert _claim(report, "superiority").allowed is False


class TestMaturityLadder:
    def test_p0_when_nothing_proved(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_fam("e", "elevate", [{"kind": "code", "path": "src/x.py"}])])
        assert ProofLedger(tmp_path).verify().maturity_level == "P-0"

    def test_p0_when_only_artifacts_are_mapped(self, tmp_path: Path) -> None:
        _write_matrix(tmp_path, [_fam("e", "elevate", [{"kind": "code", "path": "src/e.py"}])])
        _identity_docs(tmp_path)
        _touch(tmp_path, "src/e.py")
        assert ProofLedger(tmp_path).verify().maturity_level == "P-0"


class TestBaselineStatus:
    def test_reports_exists_and_calibrated(self, tmp_path: Path) -> None:
        gate = ClaimGate(tmp_path)
        assert gate.baseline_status() == (False, False)
        (tmp_path / "benchmarks").mkdir()
        (tmp_path / "benchmarks" / "gsd-baseline.json").write_text(json.dumps({"calibrated": True}))
        assert gate.baseline_status() == (True, True)


class TestRealRepoMatrix:
    """Verify the shipped matrix against the live repo — the integration check."""

    def test_real_matrix_is_internally_consistent(self) -> None:
        report = ProofLedger(_repo_root()).verify()
        unmapped = [
            f.id
            for f in report.families
            if f.classification in ("inherit", "elevate") and f.state != "mapped"
        ]
        assert unmapped == [], f"unmapped capability families: {unmapped}"
        assert report.total_families >= 12
        assert _claim(report, "identity").allowed is True
        assert _claim(report, "superset").allowed is False
        assert _claim(report, "superiority").allowed is False
        assert report.maturity_level == "P-0"

    def test_all_families_mapped_but_behavior_claims_still_gated(self) -> None:
        report = ProofLedger(_repo_root()).verify()
        by_id = {f.id: f for f in report.families}
        assert by_id["standards-compliance-audit"].state == "mapped"
        assert by_id["operator-model"].state == "mapped"
        assert report.mapped == report.total_families
        assert report.proved == 0
        assert _claim(report, "superiority").allowed is False

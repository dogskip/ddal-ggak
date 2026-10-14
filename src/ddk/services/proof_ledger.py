"""Proof Program — the executable Claim Gate.

This component audits ddalggak's own comparative claims and mechanically refuses
to overclaim.

``ProofLedger`` resolves the public capability catalog against local files. ``ClaimGate``
checks required evidence without treating path coverage as behavioral verification.
See ``benchmarks/README.md`` for optional local inputs and claim limitations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final, cast

from ddk.models.proof import (
    CapabilityFamily,
    ClaimGateResult,
    EvidenceRef,
    MaturityLevel,
    ProofReport,
)
from ddk.security.repo_paths import UnsafeRepositoryPathError, resolve_within_repository

_DEFAULT_MATRIX: Final = "benchmarks/capability-matrix.json"
_BASELINE: Final = "benchmarks/gsd-baseline.json"
_COMPARATIVE: Final = "benchmarks/comparative-scorecard.json"
_IDENTITY_DOC: Final = "docs/design/27-identity-positioning.md"
_PRD_DOC: Final = "docs/design/02-prd.md"


class MatrixLoadError(RuntimeError):
    """Raised when the capability matrix source cannot be parsed."""


class ClaimGate:
    """Evaluate claim conditions against resolved evidence.

    Pure with respect to its inputs except for filesystem probes under
    ``repo_root`` (baseline / comparative artifacts).
    """

    def __init__(self, repo_root: Path) -> None:
        self._root = repo_root

    def evaluate(self, families: list[CapabilityFamily]) -> list[ClaimGateResult]:
        results = [self._identity()]
        results.extend(self._parity(fam) for fam in families)
        results.append(self._superset(families))
        results.append(self._superiority(families))
        return results

    # -- individual gates -------------------------------------------------

    def _identity(self) -> ClaimGateResult:
        """Require both optional local identity and requirements documents."""
        identity_exists = (self._root / _IDENTITY_DOC).exists()
        prd_exists = (self._root / _PRD_DOC).exists()
        satisfied: list[str] = []
        unmet: list[str] = []
        (satisfied if identity_exists else unmet).append(f"{_IDENTITY_DOC} present")
        (satisfied if prd_exists else unmet).append(f"{_PRD_DOC} present")
        return ClaimGateResult(
            claim_type="identity",
            allowed=identity_exists and prd_exists,
            satisfied=satisfied,
            unmet=unmet,
            evidence=[
                EvidenceRef(kind="doc", path=_IDENTITY_DOC, exists=identity_exists),
                EvidenceRef(kind="doc", path=_PRD_DOC, exists=prd_exists),
            ],
        )

    def _parity(self, fam: CapabilityFamily) -> ClaimGateResult:
        """doc 28 §Parity Claim — row + impl/test evidence + gate green."""
        proved = fam.state == "proved"
        present = [ref for ref in fam.evidence if ref.exists]
        missing = [ref for ref in fam.evidence if not ref.exists]
        satisfied = [f"evidence resolves: {ref.path}" for ref in present]
        unmet = [f"evidence missing: {ref.path}" for ref in missing]
        if not fam.evidence:
            unmet.append("no evidence declared")
        elif fam.state == "mapped":
            unmet.append("behavior verification receipt missing")
        return ClaimGateResult(
            claim_type="parity",
            subject=fam.id,
            allowed=proved,
            satisfied=satisfied,
            unmet=unmet,
            evidence=fam.evidence,
        )

    def _superset(self, families: list[CapabilityFamily]) -> ClaimGateResult:
        """doc 28 §Superset Claim — identity + every inherit/elevate family proved."""
        identity_ok = self._identity().allowed
        mapped = [f for f in families if f.classification in ("inherit", "elevate")]
        unproved = [f for f in mapped if f.state != "proved"]
        satisfied: list[str] = []
        unmet: list[str] = []
        (satisfied if identity_ok else unmet).append("identity claim allowed")
        (satisfied if families else unmet).append("core capability families present")
        if unproved:
            unmet.extend(f"inherit/elevate family not proved: {f.id}" for f in unproved)
        else:
            satisfied.append("all inherit/elevate families proved")
        allowed = identity_ok and bool(families) and not unproved
        return ClaimGateResult(
            claim_type="superset",
            allowed=allowed,
            satisfied=satisfied,
            unmet=unmet,
        )

    def _superiority(self, families: list[CapabilityFamily]) -> ClaimGateResult:
        """doc 27 #3 — parity evidence + calibrated baseline + comparative artifact.

        This is the gate that keeps ddalggak honest: without a *calibrated*
        ``gsd-baseline.json`` and a comparative artifact, superiority is denied
        no matter how much parity evidence exists.
        """
        any_parity = any(f.state == "proved" for f in families)
        baseline_exists, calibrated = self.baseline_status()
        comparative_exists = (self._root / _COMPARATIVE).exists()
        satisfied: list[str] = []
        unmet: list[str] = []
        (satisfied if any_parity else unmet).append("parity evidence present")
        (satisfied if baseline_exists else unmet).append(f"{_BASELINE} present")
        (satisfied if calibrated else unmet).append("baseline calibrated (calibrated == true)")
        (satisfied if comparative_exists else unmet).append(
            f"{_COMPARATIVE} present (measured comparison)"
        )
        allowed = any_parity and baseline_exists and calibrated and comparative_exists
        return ClaimGateResult(
            claim_type="superiority",
            allowed=allowed,
            satisfied=satisfied,
            unmet=unmet,
        )

    def baseline_status(self) -> tuple[bool, bool]:
        """Return (exists, calibrated). Malformed JSON is treated as uncalibrated."""
        path = self._root / _BASELINE
        if not path.exists():
            return (False, False)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return (True, False)
        return (True, bool(data.get("calibrated", False)))


class ProofLedger:
    """Load the capability matrix, resolve evidence, and produce a ProofReport."""

    def __init__(self, repo_root: Path, matrix_path: Path | None = None) -> None:
        self._root = repo_root
        self._matrix_path = matrix_path or (repo_root / _DEFAULT_MATRIX)
        self._gate = ClaimGate(repo_root)

    def load_matrix(self) -> list[CapabilityFamily]:
        try:
            raw = json.loads(self._matrix_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise MatrixLoadError(f"capability matrix not found: {self._matrix_path}") from exc
        except json.JSONDecodeError as exc:
            raise MatrixLoadError(f"capability matrix is not valid JSON: {exc}") from exc
        families = raw.get("families")
        if not isinstance(families, list):
            raise MatrixLoadError("capability matrix missing 'families' array")
        return [CapabilityFamily.model_validate(item) for item in cast(list[object], families)]

    def verify(self) -> ProofReport:
        families = self._resolve(self.load_matrix())
        claims = self._gate.evaluate(families)
        maturity = self._maturity(claims)
        return ProofReport(
            families=families,
            claims=claims,
            maturity_level=maturity,
            summary=self._summary(families, claims, maturity),
        )

    # -- internals --------------------------------------------------------

    def _resolve(self, families: list[CapabilityFamily]) -> list[CapabilityFamily]:
        for fam in families:
            for ref in fam.evidence:
                try:
                    path = resolve_within_repository(self._root, ref.path)
                except UnsafeRepositoryPathError as exc:
                    ref.exists = False
                    ref.resolution_error = str(exc)
                else:
                    ref.exists = path.exists()
                    ref.resolution_error = None
        return families

    def _maturity(self, claims: list[ClaimGateResult]) -> MaturityLevel:
        """Map evidence + claims onto the doc 27 maturity ladder (top-down)."""
        allowed = {c.claim_type for c in claims if c.allowed}
        baseline_exists, calibrated = self._gate.baseline_status()
        if "superiority" in allowed:
            return "P-4"
        if baseline_exists and calibrated:
            return "P-3"
        if "superset" in allowed:
            return "P-2"
        if "identity" in allowed and "parity" in allowed:
            return "P-1"
        return "P-0"

    def _summary(
        self,
        families: list[CapabilityFamily],
        claims: list[ClaimGateResult],
        maturity: MaturityLevel,
    ) -> str:
        proved = sum(1 for f in families if f.state == "proved")
        mapped = sum(1 for f in families if f.state == "mapped")
        allowed = sorted({c.claim_type for c in claims if c.allowed})
        denied = sorted({c.claim_type for c in claims if not c.allowed})
        allowed_str = ", ".join(allowed) if allowed else "none"
        denied_str = ", ".join(denied) if denied else "none"
        return (
            f"{mapped}/{len(families)} capability families mapped · "
            f"{proved}/{len(families)} behavior-proved · "
            f"maturity {maturity} · allowed claims: {allowed_str} · "
            f"denied: {denied_str}"
        )

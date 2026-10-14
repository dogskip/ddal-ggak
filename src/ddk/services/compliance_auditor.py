"""Standards Compliance Auditor — clause-to-artifact coverage gate.

A *new-target* capability (doc 28): maps recognized standard clauses to the design
artifacts expected to address them, resolves those artifacts on disk, and reports
honest coverage — mapped / partial / gap — never a certification claim.

Mirrors the Proof Program's design: a JSON catalog is the source of truth, status
is computed from the filesystem, and gaps are surfaced rather than hidden.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, cast

from ddk.models.compliance import ComplianceReport, StandardClause
from ddk.security.repo_paths import UnsafeRepositoryPathError, resolve_within_repository

_DEFAULT_CATALOG: Final = "benchmarks/standards-catalog.json"
_REPORT_OUT: Final = "benchmarks/compliance-matrix.json"


class CatalogLoadError(RuntimeError):
    """Raised when the standards catalog cannot be parsed."""


class ComplianceAuditor:
    """Load the clause catalog, resolve artifacts, and produce a ComplianceReport."""

    def __init__(self, repo_root: Path, catalog_path: Path | None = None) -> None:
        self._root = repo_root
        self._catalog_path = catalog_path or (repo_root / _DEFAULT_CATALOG)

    def load_catalog(self) -> list[StandardClause]:
        try:
            raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CatalogLoadError(f"standards catalog not found: {self._catalog_path}") from exc
        except json.JSONDecodeError as exc:
            raise CatalogLoadError(f"standards catalog is not valid JSON: {exc}") from exc
        clauses = raw.get("clauses")
        if not isinstance(clauses, list):
            raise CatalogLoadError("standards catalog missing 'clauses' array")
        return [StandardClause.model_validate(item) for item in cast(list[object], clauses)]

    def audit(self) -> ComplianceReport:
        clauses = self._resolve(self.load_catalog())
        return ComplianceReport(clauses=clauses, summary=self._summary(clauses))

    def write_matrix(self, report: ComplianceReport, out_path: Path | None = None) -> Path:
        """Persist the audit as benchmarks/compliance-matrix.json. Returns the path."""
        target = out_path or (self._root / _REPORT_OUT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target

    # -- internals --------------------------------------------------------

    def _resolve(self, clauses: list[StandardClause]) -> list[StandardClause]:
        for clause in clauses:
            for ref in clause.artifacts:
                try:
                    path = resolve_within_repository(self._root, ref.path)
                except UnsafeRepositoryPathError as exc:
                    ref.exists = False
                    ref.resolution_error = str(exc)
                else:
                    ref.exists = path.exists()
                    ref.resolution_error = None
        return clauses

    def _summary(self, clauses: list[StandardClause]) -> str:
        total = len(clauses)
        mapped = sum(1 for c in clauses if c.status == "mapped")
        partial = sum(1 for c in clauses if c.status == "partial")
        gaps = sum(1 for c in clauses if c.status == "gap")
        standards = len({c.standard for c in clauses})
        coverage = round(mapped / total, 4) if total else 0.0
        return (
            f"{mapped}/{total} clauses mapped across {standards} standard(s) · "
            f"coverage {coverage:.0%} · partial {partial} · gaps {gaps}"
        )

    def per_standard(self, report: ComplianceReport) -> dict[str, dict[str, Any]]:
        """Coverage rollup keyed by standard — for grouped CLI output."""
        rollup: dict[str, dict[str, Any]] = {}
        for clause in report.clauses:
            bucket = rollup.setdefault(
                clause.standard, {"total": 0, "mapped": 0, "partial": 0, "gap": 0}
            )
            bucket["total"] += 1
            bucket[clause.status] += 1
        return rollup

"""WorkspaceManager — manages the .ddk/ workspace directory — INFRA-07."""

from __future__ import annotations

import json
from pathlib import Path

_SCHEMA_VERSION = "1"


class WorkspaceManager:
    """Manages the project-local ``.ddk/`` workspace directory.

    Idempotent: calling :meth:`init` multiple times on the same path is safe.

    Args:
        project_root: Root directory of the target project.
    """

    def __init__(self, project_root: Path) -> None:
        self.root: Path = project_root / ".ddk"

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init(self) -> None:
        """Create the ``.ddk/`` directory structure if not already present.

        Creates:
        - ``.ddk/``
        - ``.ddk/cases/``
        - ``.ddk/schema-version.json``
        """
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "cases").mkdir(exist_ok=True)

        version_file = self.root / "schema-version.json"
        if not version_file.exists():
            version_file.write_text(
                json.dumps({"schema_version": _SCHEMA_VERSION}, indent=2) + "\n",
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # Case ID management
    # ------------------------------------------------------------------

    def next_case_id(self) -> str:
        """Compute the next sequential case ID (e.g., ``C-001``, ``C-002``).

        Counts existing ``C-NNN`` directories under ``.ddk/cases/`` to determine
        the next number. Always zero-pads to 3 digits.

        Returns:
            Case ID string like ``"C-007"``.
        """
        cases_dir = self.root / "cases"
        if not cases_dir.exists():
            return "C-001"

        existing = sorted(
            p.name
            for p in cases_dir.iterdir()
            if p.is_dir() and p.name.startswith("C-") and p.name[2:].isdigit()
        )
        if not existing:
            return "C-001"

        last_num = int(existing[-1][2:])
        return f"C-{last_num + 1:03d}"

    # ------------------------------------------------------------------
    # Case directory
    # ------------------------------------------------------------------

    def case_dir(self, case_id: str) -> Path:
        """Return the path to an existing or future case directory.

        Args:
            case_id: Case ID string such as ``"C-001"``.

        Returns:
            ``Path`` object (may not exist yet).
        """
        return self.root / "cases" / case_id

    def init_case(self, case_id: str) -> Path:
        """Create all subdirectories for a new case.

        Creates:
        - ``artifacts/``
        - ``reports/``
        - ``fix-attempts/``
        - ``llm-calls/``
        - ``screenshots/``

        Args:
            case_id: Case ID string such as ``"C-001"``.

        Returns:
            Path to the case directory.
        """
        case_path = self.case_dir(case_id)
        for sub in ("artifacts", "reports", "fix-attempts", "llm-calls", "screenshots"):
            (case_path / sub).mkdir(parents=True, exist_ok=True)
        return case_path

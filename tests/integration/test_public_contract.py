"""The public source package must validate records without private design files."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_contract_validation_without_private_documents(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[2]
    shutil.copytree(
        project / "src/ddk",
        tmp_path / "ddk",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from ddk.models.verified_change import ContractError, validate_structure\n"
            "try:\n"
            "    validate_structure({})\n"
            "except ContractError as error:\n"
            "    assert str(error).startswith('schema:')\n"
            "else:\n"
            "    raise AssertionError('Invalid record accepted')\n",
        ],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr

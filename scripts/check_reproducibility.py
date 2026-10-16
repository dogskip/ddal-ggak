"""Run the fixed repository matrix and reject incomplete verification receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

REPOSITORIES = ("python", "javascript", "browser")
VARIANTS = ("ready", "target-missed", "regression")
RUNTIMES = ("host", "isolated")


def summarize(
    rows: list[dict[str, Any]],
    *,
    pytest_exit: int,
    skipped: int,
    runtimes: tuple[str, ...] = RUNTIMES,
) -> dict[str, Any]:
    expected = {(r, p, v) for r in runtimes for p in REPOSITORIES for v in VARIANTS}
    actual = [(r.get("runtime"), r.get("repository"), r.get("variant")) for r in rows]
    problems = []
    if set(actual) != expected or len(actual) != len(expected):
        problems.append("matrix_incomplete_or_duplicated")
    if pytest_exit != 0 or skipped != 0:
        problems.append("pytest_failed_or_skipped")
    for row in rows:
        wanted = "ready" if row.get("variant") == "ready" else "blocked"
        if row.get("decision") != wanted or row.get("replay_decision") != wanted:
            problems.append("unexpected_decision")
        if any(
            row.get(key) is not True
            for key in ("evidence_integrity", "source_preserved", "cleanup_complete")
        ):
            problems.append("evidence_incomplete")
        if any(
            type(row.get(key)) is not int or row[key] != 0
            for key in ("model_calls", "actual_cost_micro_usd")
        ):
            problems.append("unexpected_or_unknown_model_cost")
        duration = row.get("duration_s")
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
            problems.append("duration_invalid")
    return {
        "format": "ddk-reproduction/1",
        "status": "failed" if problems else "passed",
        "runs": len(rows),
        "expected_runs": len(expected),
        "ready": sum(r.get("decision") == "ready" for r in rows),
        "expected_blocked": sum(
            r.get("variant") in {"target-missed", "regression"} and r.get("decision") == "blocked"
            for r in rows
        ),
        "model_calls": sum(r["model_calls"] for r in rows)
        if all(type(r.get("model_calls")) is int for r in rows)
        else None,
        "actual_cost_micro_usd": sum(r["actual_cost_micro_usd"] for r in rows)
        if all(type(r.get("actual_cost_micro_usd")) is int for r in rows)
        else None,
        "repair_success_rate": None,
        "independent_user_success_rate": None,
        "pytest_exit": pytest_exit,
        "skipped": skipped,
        "problems": sorted(set(problems)),
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--runtime", choices=(*RUNTIMES, "all"), default="all")
    parser.add_argument(
        "--installed",
        action="store_true",
        help="Require ddk from this Python environment's installed wheel.",
    )
    args = parser.parse_args()
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=False)
    repository = Path(__file__).resolve().parents[1]
    files = [Path(__file__), repository / "tests/e2e/test_repository_reproduction.py"]
    files += sorted((repository / "tests/fixtures/reproduction").rglob("*"))
    frozen = {
        str(p.relative_to(repository)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
        if p.is_file() and "__pycache__" not in p.parts
    }
    (output / "inputs.json").write_text(json.dumps(frozen, indent=2) + "\n")
    runtimes = RUNTIMES if args.runtime == "all" else (args.runtime,)
    environment = dict(os.environ)
    environment.update(DDK_REPRO_EVIDENCE_DIR=str(output), DDK_E2E="1")
    for key in ("ANTHROPIC_API_KEY", "DDK_ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        environment.pop(key, None)
    if "isolated" in runtimes:
        environment["DDK_DOCKER_E2E"] = "1"
    if args.installed:
        environment["DDK_REPRO_EXPECT_INSTALLED"] = "1"
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "tests/e2e/test_repository_reproduction.py",
        "-q",
        f"--junitxml={output / 'pytest.xml'}",
    ]
    if args.runtime != "all":
        argv += ["-k", args.runtime]
    if args.installed:
        argv += ["-o", f"pythonpath={repository}"]
    with (output / "pytest.txt").open("w") as log:
        result = subprocess.run(
            argv, cwd=repository, env=environment, stdout=log, stderr=subprocess.STDOUT, check=False
        )
    report = output / "pytest.xml"
    skipped = len(list(ElementTree.parse(report).iter("skipped"))) if report.is_file() else 1
    rows = [json.loads(p.read_text()) for p in sorted((output / "receipts").glob("*.json"))]
    summary = summarize(rows, pytest_exit=result.returncode, skipped=skipped, runtimes=runtimes)
    summary["installed_package_required"] = args.installed
    if any(
        hashlib.sha256((repository / p).read_bytes()).hexdigest() != h for p, h in frozen.items()
    ):
        summary["status"] = "failed"
        summary["problems"].append("input_changed_during_run")
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

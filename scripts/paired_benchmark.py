"""Prepare pinned sources and independent oracles; never invoke a coding model."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

from ddk.adapters.subprocess_build_runner import start_owned_process, stop_owned_process
from ddk.models.verified_change import MAX_RECORD_BYTES, canonical_json, decode_json, record_digest
from ddk.security.file_access import read_regular
from ddk.security.repo_paths import resolve_within_repository
from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.case_criteria import compile_checks
from ddk.services.case_discovery import has_acceptance
from ddk.services.durable_files import atomic_write
from ddk.services.paired_benchmark import corpus
from ddk.services.source_snapshot import (
    capture_git_source,
    capture_source,
    manifest_digest,
    materialize_snapshot,
)
from ddk.services.verified_change_service import VerifiedChangeService
from ddk.services.verified_change_store import VerifiedChangeStore
from ddk.services.verified_host import observe_environment

_LIMIT = 64 * 1024**2
_SCRIPT = Path(__file__).resolve()
_PYTHON = r"""
import json,sys
from pathlib import Path
import click
assert Path(click.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()/'src')
def check(fn):
    try: return bool(fn())
    except Exception: return False
checks=[check(lambda:click.format_filename('/scope/name.txt',shorten=True)=='name.txt'),
        check(lambda:click.format_filename('/scope/name.txt')=='/scope/name.txt'),
        check(lambda:click.format_filename(b'/scope/\xff.txt',shorten=True)=='\ufffd.txt')]
print(json.dumps({'executed_count':len(checks),'failed_count':checks.count(False),'skipped_count':0}))
"""
_JAVASCRIPT = r"""
import {readFileSync} from 'node:fs';
const encoded=readFileSync(process.argv[1]).toString('base64');
const {clsx}=await import('data:text/javascript;base64,'+encoded);
const check=fn=>{try{return !!fn()}catch{return false}};
const checks=[check(()=>clsx({active:true,hidden:false})==='active'),
              check(()=>clsx('x',['y'],null)==='x y'),
              check(()=>clsx(['alpha',[{beta:1,ghost:0}]],0,NaN)==='alpha beta')];
console.log(JSON.stringify({executed_count:checks.length,failed_count:checks.filter(x=>!x).length,skipped_count:0}));
"""
_VIEW = r"""
var benchmarkNode = document.createElement('div'); document.body.append(benchmarkNode);
app({init:0,node:benchmarkNode,view:state=>h('main',{},[
  h('h1',{},text('Counter')),h('output',{id:'count'},text(state)),
  h('button',{id:'add',onclick:state=>state+1},text('Add one')),
  h('button',{id:'reset',onclick:()=>0},text('Reset'))])});
"""


def case_draft(task):
    if task["id"] == "hyperapp-events":
        target = [
            {"action": "click", "selector": "#add"},
            {"action": "expect-text", "selector": "#count", "value": "1"},
            {"action": "click", "selector": "#reset"},
            {"action": "expect-text", "selector": "#count", "value": "0"},
        ]
        preserve = [
            {"action": "expect-text", "selector": "h1", "value": "Counter"},
            {"action": "expect-text", "selector": "#count", "value": "0"},
        ]
    else:
        expected, preserved = (
            ("name.txt", "/scope/name.txt")
            if task["id"] == "click-short-name"
            else ("active", "x y")
        )
        target = [{"action": "expect-text", "selector": "#result", "value": expected}]
        preserve = [{"action": "expect-text", "selector": "#result", "value": preserved}]
    config = {
        "draft": True,
        "scope_paths": [task["source_path"]],
        "preview_argv": ["python3", "ddk_benchmark_fixture.py", task["id"], "{port}"],
        "limits": {"max_provider_requests": 0, "budget_micro_usd": 0, "max_fix_attempts": 0},
        "checks": [
            {
                "check_id": role,
                "role": role,
                "kind": "browser",
                "entry_path": "/" + role,
                "viewport": {"width": 800, "height": 600},
                "steps": steps,
            }
            for role, steps in (("target", target), ("preserve", preserve))
        ],
    }
    compile_checks(config, "0" * 64)
    return config


def fixture_program(plan):
    content = files("ddk").joinpath("assets/benchmarks/browser-fixture.py.txt").read_bytes()
    if hashlib.sha256(content).hexdigest() != plan["fixture_sha256"]:
        raise ValueError("benchmark_fixture_changed")
    return content


def _create_baseline(candidate):
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_ATTR_NOSYSTEM="1")
    commands = [
        ["init", "--template=", "-q", "-b", "bench-source", str(candidate)],
        ["-C", str(candidate), "add", "."],
        [
            "-C",
            str(candidate),
            "-c",
            "user.name=DDK Benchmark",
            "-c",
            "user.email=benchmark@example.invalid",
            "commit",
            "-qm",
            "test: freeze controlled regression",
        ],
    ]
    for command in commands:
        subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "commit.gpgsign=false",
                *command,
            ],
            env=environment,
            timeout=30,
            check=True,
            capture_output=True,
        )


def _browser_probe(repository):
    from playwright.sync_api import expect, sync_playwright

    source = read_regular(repository / "index.js", 2 * 1024**2).decode("utf-8")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=os.environ["DDK_BENCH_CHROMIUM"], headless=True, chromium_sandbox=True
        )
        try:
            page = browser.new_page()
            page.route("**/*", lambda route: route.abort())
            errors = []
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.goto("about:blank")
            page.add_script_tag(type="module", content=source + _VIEW)

            def equals(selector, value):
                try:
                    expect(page.locator(selector)).to_have_text(value, timeout=800)
                    return True
                except AssertionError:
                    return False

            initial = equals("h1", "Counter") and equals("#count", "0")
            page.locator("#add").click(timeout=800)
            target = equals("#count", "1")
            page.locator("#add").click(timeout=800)
            repeated = equals("#count", "2")
            page.locator("#reset").click(timeout=800)
            reset = equals("#count", "0")
            checks = [initial, target, repeated and reset]
            if errors:
                checks = [False] * 3
            return {"executed_count": 3, "failed_count": checks.count(False), "skipped_count": 0}
        finally:
            browser.close()


def _worker(task, repository):
    if task.startswith("click-"):
        environment = {**os.environ, "PYTHONPATH": str(repository / "src")}
        os.execve(sys.executable, [sys.executable, "-c", _PYTHON, str(repository)], environment)
    elif task.startswith("clsx-"):
        os.execvp(
            "node",
            ["node", "--input-type=module", "-e", _JAVASCRIPT, str(repository / "src/index.js")],
        )
    else:
        print(json.dumps(_browser_probe(repository)))


async def oracle(args):
    if not args.trusted_local:
        raise ValueError("explicit_trusted_local_required")
    started = time.monotonic_ns()
    plan, _ = corpus()
    if hashlib.sha256(read_regular(_SCRIPT, 2 * 1024**2)).hexdigest() != plan["oracle_sha256"]:
        raise ValueError("oracle_program_changed")
    if args.task not in {task["id"] for task in plan["tasks"]}:
        raise ValueError("unknown_corpus_task")
    repository = args.repo.resolve()
    before = capture_source(repository, max_total_bytes=_LIMIT)
    environment = {
        name: os.environ[name]
        for name in ("PATH", "LANG", "SYSTEMROOT", "PLAYWRIGHT_BROWSERS_PATH")
        if name in os.environ
    }
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if args.task.startswith("hyperapp-"):
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            environment["DDK_BENCH_CHROMIUM"] = playwright.chromium.executable_path
    with tempfile.TemporaryDirectory(prefix="ddk-oracle-") as temporary:
        environment["HOME"] = temporary
        command = [
            sys.executable,
            str(_SCRIPT),
            "_worker",
            args.task,
            str(repository),
            "--trusted-local",
        ]
        process, output = await start_owned_process(
            command, Path(temporary), environment=environment, max_output_bytes=1024**2
        )
        code = 4
        try:
            if await output.wait(time.monotonic_ns() + 30_000_000_000):
                raise ValueError("oracle_output_limit")
            code = process.returncode or 0
        except TimeoutError:
            code = 4
        finally:
            await stop_owned_process(process, output)
        stdout, _ = output.text()
    try:
        observation = json.loads(stdout) if code == 0 else {}
        counts = {
            key: observation[key] for key in ("executed_count", "failed_count", "skipped_count")
        }
        if any(type(v) is not int or v < 0 for v in counts.values()):
            raise ValueError("invalid_oracle_counts")
    except (ValueError, KeyError, TypeError):
        counts = {"executed_count": 0, "failed_count": 0, "skipped_count": 0}
        code = 4
    after = capture_source(repository, max_total_bytes=_LIMIT)
    if after.tree_sha256 != before.tree_sha256:
        raise ValueError("oracle_source_changed")
    report = {
        "format": "ddk-benchmark-oracle/1",
        "task_id": args.task,
        "seed": args.seed,
        "arm": args.arm,
        "candidate_tree_sha256": before.tree_sha256,
        "duration_ms": (time.monotonic_ns() - started) // 1_000_000,
        "oracle_sha256": hashlib.sha256(read_regular(_SCRIPT, 2 * 1024**2)).hexdigest(),
        **counts,
    }
    payload = canonical_json(report)
    if args.out:
        atomic_write(args.out.parent.resolve() / args.out.name, payload, exclusive=True)
    print(payload.decode())
    return code or int(
        counts["executed_count"] == 0 or counts["failed_count"] > 0 or counts["skipped_count"] > 0
    )


def prepare(args):
    plan, digest = corpus()
    if hashlib.sha256(read_regular(_SCRIPT, 2 * 1024**2)).hexdigest() != plan["oracle_sha256"]:
        raise ValueError("oracle_program_changed")
    fixture = fixture_program(plan)
    sources = dict(item.split("=", 1) for item in args.source)
    if len(sources) != len(args.source):
        raise ValueError("duplicate_source")
    if set(sources) != {task["id"].split("-")[0] for task in plan["tasks"]}:
        raise ValueError("three_pinned_sources_required")
    output = args.out.parent.resolve() / args.out.name
    output.mkdir(mode=0o700)
    rows = []
    drafts = {}
    (output / "case-drafts").mkdir(mode=0o700)
    for task in plan["tasks"]:
        draft_path = f"case-drafts/{task['id']}.json"
        payload = canonical_json(case_draft(task))
        atomic_write(output / draft_path, payload, exclusive=True)
        drafts[task["id"]] = {"path": draft_path, "sha256": hashlib.sha256(payload).hexdigest()}
        source = Path(sources[task["id"].split("-")[0]]).resolve()
        snapshot = capture_git_source(source, task["commit"], max_total_bytes=_LIMIT)
        if snapshot.tree_sha256 != task["source_tree_sha256"]:
            raise ValueError("pinned_source_tree_mismatch")
        target = next(file for file in snapshot.files if file.path == task["source_path"])
        if (
            target.sha256 != task["source_sha256"]
            or target.content.count(task["before"].encode()) != 1
        ):
            raise ValueError("pinned_source_mismatch")
        for seed in plan["seeds"]:
            initial = None
            for arm in ("plain", "ddk"):
                relative = f"{task['id']}/{seed}/{arm}"
                candidate = output / relative
                materialize_snapshot(snapshot, candidate)
                atomic_write(
                    candidate / "ddk_benchmark_fixture.py", fixture, mode=0o644, exclusive=True
                )
                file = candidate / task["source_path"]
                atomic_write(
                    file,
                    target.content.replace(task["before"].encode(), task["after"].encode(), 1),
                    mode=target.mode,
                )
                _create_baseline(candidate)
                tree = capture_source(candidate, max_total_bytes=_LIMIT).tree_sha256
                if initial is not None and initial != tree:
                    raise ValueError("initial_pair_mismatch")
                initial = tree
                rows.append(
                    {
                        "task_id": task["id"],
                        "seed": seed,
                        "arm": arm,
                        "candidate": relative,
                        "upstream_commit": task["commit"],
                        "initial_tree_sha256": tree,
                        "prompt_sha256": hashlib.sha256(task["request"].encode()).hexdigest(),
                        "request": task["request"],
                        "approved_case_sha256": None,
                    }
                )
    result = {
        "format": "ddk-paired-preparation/1",
        "corpus_sha256": digest,
        "oracle_sha256": plan["oracle_sha256"],
        "status": "criteria-approval-required",
        "model_calls": 0,
        "calibrated": False,
        "case_drafts": drafts,
        "rows": rows,
    }
    atomic_write(output / "preparation.json", canonical_json(result), exclusive=True)
    print(json.dumps({"contexts": len(rows), "model_calls": 0, "calibrated": False}))
    return 0


async def seal(args):
    plan, digest = corpus()
    tasks = {task["id"]: task for task in plan["tasks"]}
    approvals = dict(item.split("=", 1) for item in args.approved_draft)
    if len(approvals) != len(args.approved_draft) or set(approvals) != set(tasks):
        raise ValueError("exact_draft_approvals_required")
    fixture_program(plan)
    if hashlib.sha256(read_regular(_SCRIPT, MAX_RECORD_BYTES)).hexdigest() != plan["oracle_sha256"]:
        raise ValueError("oracle_program_changed")
    path = args.preparation.parent.resolve() / args.preparation.name
    raw = read_regular(path, MAX_RECORD_BYTES)
    manifest = decode_json(raw)
    if (
        manifest["format"] != "ddk-paired-preparation/1"
        or manifest["status"] != "criteria-approval-required"
        or manifest["corpus_sha256"] != digest
        or manifest["oracle_sha256"] != plan["oracle_sha256"]
        or set(manifest["case_drafts"]) != set(tasks)
    ):
        raise ValueError("comparison_preparation_mismatch")
    output = args.out.parent.resolve() / args.out.name
    if output.exists() or output.is_symlink():
        raise FileExistsError("sealing_output_exists")
    configurations = {}
    for name, reference in manifest["case_drafts"].items():
        payload = read_regular(
            resolve_within_repository(path.parent, reference["path"]), MAX_RECORD_BYTES
        )
        if hashlib.sha256(payload).hexdigest() != approvals[name]:
            raise ValueError("approved_draft_mismatch")
        draft = decode_json(payload)
        if draft.get("draft") is not True or draft.get("scope_paths") != [
            tasks[name]["source_path"]
        ]:
            raise ValueError("benchmark_draft_scope_mismatch")
        compile_checks(draft, "0" * 64)
        if not has_acceptance(draft):
            raise ValueError("benchmark_acceptance_required")
        configurations[name] = {**draft, "draft": False}
    candidates = {}
    expected = {
        (name, seed, arm) for name in tasks for seed in plan["seeds"] for arm in ("plain", "ddk")
    }
    for row in manifest["rows"]:
        key = (row["task_id"], row["seed"], row["arm"])
        if key not in expected or key in candidates or row["candidate"] != "/".join(map(str, key)):
            raise ValueError("comparison_matrix_invalid")
        task = tasks[row["task_id"]]
        if (
            row["upstream_commit"] != task["commit"]
            or row["request"] != task["request"]
            or row["prompt_sha256"] != hashlib.sha256(task["request"].encode()).hexdigest()
        ):
            raise ValueError("comparison_inputs_mismatch")
        fixture = resolve_within_repository(
            path.parent, row["candidate"] + "/ddk_benchmark_fixture.py"
        )
        candidate = fixture.parent
        if output.is_relative_to(candidate):
            raise ValueError("sealing_output_inside_candidate")
        if (candidate / ".ddk").exists() or (candidate / ".ddk").is_symlink():
            raise ValueError("comparison_context_not_fresh")
        snapshot = capture_source(candidate, max_total_bytes=_LIMIT)
        if (
            hashlib.sha256(read_regular(fixture, MAX_RECORD_BYTES)).hexdigest()
            != plan["fixture_sha256"]
            or snapshot.tree_sha256 != row["initial_tree_sha256"]
        ):
            raise ValueError("comparison_initial_tree_mismatch")
        original = []
        for source in snapshot.files:
            if source.path == "ddk_benchmark_fixture.py":
                continue
            if source.path == task["source_path"]:
                broken, corrected = task["after"].encode(), task["before"].encode()
                matches = []
                position = source.content.find(broken)
                attempts = 0
                while position >= 0 and attempts < 16:
                    restored = (
                        source.content[:position]
                        + corrected
                        + source.content[position + len(broken) :]
                    )
                    if hashlib.sha256(restored).hexdigest() == task["source_sha256"]:
                        matches.append(restored)
                    attempts += 1
                    position = source.content.find(broken, position + len(broken))
                if position >= 0 or len(matches) != 1:
                    raise ValueError("comparison_regression_mismatch")
                content = matches[0]
                source = replace(
                    source,
                    content=content,
                    sha256=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                )
            original.append(source)
        if manifest_digest(original) != task["source_tree_sha256"]:
            raise ValueError("comparison_upstream_tree_mismatch")
        candidates[key] = candidate
    if set(candidates) != expected:
        raise ValueError("comparison_matrix_incomplete")
    for name in tasks:
        hashes = {row["initial_tree_sha256"] for row in manifest["rows"] if row["task_id"] == name}
        if len(hashes) != 1:
            raise ValueError("comparison_initial_tree_mismatch")
    cases = {}
    for name, task in tasks.items():
        first = candidates[name, plan["seeds"][0], "ddk"]
        env = await observe_environment(first)
        case = await CaseBootstrapper(first).initialize(
            task["request"], configuration=configurations[name], observed_environment=env
        )
        if case.get("status") == "blocked":
            raise ValueError("benchmark_acceptance_required")
        case_path = (
            VerifiedChangeStore(first, create=False).path_for("case", case["case_id"]) / "case.json"
        )
        if case["baseline_tree_sha256"] not in {
            row["initial_tree_sha256"] for row in manifest["rows"] if row["task_id"] == name
        }:
            raise ValueError("comparison_initial_tree_mismatch")
        for seed in plan["seeds"][1:]:
            VerifiedChangeService(candidates[name, seed, "ddk"]).import_case(case_path)
        cases[name] = {
            "case_id": case["case_id"],
            "case_sha256": record_digest(case),
            "approved_draft_sha256": approvals[name],
            "case_path": case_path.relative_to(path.parent).as_posix(),
        }
    for row in manifest["rows"]:
        if (
            capture_source(
                candidates[row["task_id"], row["seed"], row["arm"]], max_total_bytes=_LIMIT
            ).tree_sha256
            != row["initial_tree_sha256"]
        ):
            raise ValueError("comparison_initial_tree_mismatch")
    if read_regular(path, MAX_RECORD_BYTES) != raw:
        raise ValueError("comparison_preparation_changed")
    atomic_write(
        output,
        canonical_json(
            {
                "format": "ddk-paired-cases/1",
                "corpus_sha256": digest,
                "status": "criteria-sealed",
                "preparation_sha256": hashlib.sha256(raw).hexdigest(),
                "cases": cases,
                "execution_approved": False,
                "provider_approved": False,
                "model_calls": 0,
                "calibrated": False,
            }
        ),
        exclusive=True,
    )
    print(
        json.dumps(
            {"cases": len(cases), "contexts": len(cases) * len(plan["seeds"]), "model_calls": 0}
        )
    )
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser("prepare")
    setup.add_argument("--source", action="append", required=True)
    setup.add_argument("--out", type=Path, required=True)
    freeze = commands.add_parser(
        "seal", help="Compile exactly approved drafts without executing project code."
    )
    freeze.add_argument("--preparation", type=Path, required=True)
    freeze.add_argument("--approved-draft", action="append", default=[])
    freeze.add_argument("--out", type=Path, required=True)
    evaluate = commands.add_parser("oracle")
    evaluate.add_argument("--task", required=True)
    evaluate.add_argument("--repo", type=Path, required=True)
    evaluate.add_argument("--trusted-local", action="store_true")
    evaluate.add_argument("--seed", type=int, required=True)
    evaluate.add_argument("--arm", choices=["plain", "ddk"], required=True)
    evaluate.add_argument("--out", type=Path)
    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("task")
    worker.add_argument("repo", type=Path)
    worker.add_argument("--trusted-local", action="store_true")
    args = parser.parse_args()
    if args.command == "_worker":
        if not args.trusted_local or args.task not in {task["id"] for task in corpus()[0]["tasks"]}:
            print("explicit_trusted_local_and_known_task_required", file=sys.stderr)
            return 3
        _worker(args.task, args.repo)
        return 0
    try:
        if args.command == "seal":
            return asyncio.run(seal(args))
        return prepare(args) if args.command == "prepare" else asyncio.run(oracle(args))
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as error:
        if str(error) == "exact_draft_approvals_required":
            print("exact_draft_approvals_required", file=sys.stderr)
            return 4
        print("benchmark_preparation_or_observation_failed", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

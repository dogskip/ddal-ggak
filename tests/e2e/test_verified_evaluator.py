"""Real model-free baseline/candidate checks preserve both original directories."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.models.verified_change import canonical_json, decode_json, record_digest
from ddk.services.source_snapshot import capture_source, manifest_digest
from ddk.services.verified_change_engine import VerifiedChangeEngine
from ddk.services.verified_change_store import VerifiedChangeStore
from tests.e2e.test_verified_browser import settings as settings
from tests.unit.adapters.test_verified_browser import FIXTURE, png, step
from tests.unit.adapters.test_verified_evaluator import request_for
from tests.unit.test_verified_change_engine import DATA, RUN_ID, fixed_file

pytestmark = pytest.mark.playwright

SERVER = b"""const http=require('http'),fs=require('fs');
http.createServer((req,res)=>{
  res.setHeader('Content-Type','text/html');
  res.end(fs.readFileSync(req.url==='/next'?'next.html':'index.html'));
}).listen(Number(process.argv[2]),'127.0.0.1');"""


def flow(name, steps):
    return canonical_json(
        {
            "record_type": "flow",
            "schema_version": "verified-change/1",
            "flow_id": name,
            "check_id": name,
            "entry_path": "/",
            "fixture_sha256": FIXTURE,
            "steps": steps,
        }
    )


def scenario(tmp_path, settings, candidate="ready"):
    case = copy.deepcopy(json.loads(DATA.read_text())["valid"][0]["record"])
    files = {}
    for name, title, label in [
        ("baseline", "Old", "Continue"),
        (
            "candidate",
            "Old" if candidate == "spoofed" else "New",
            "Broken" if candidate == "regression" else "Continue",
        ),
    ]:
        root = tmp_path / name
        root.mkdir()
        content = (
            f"<!doctype html><link rel='icon' href='data:,'><h1>{title}</h1>"
            f"<a href='/next'>{label}</a>"
        ).encode()
        for path, payload in {
            "index.html": content,
            "next.html": b"<!doctype html><link rel='icon' href='data:,'><h1>Next</h1>",
            "serve.cjs": SERVER,
        }.items():
            (root / path).write_bytes(payload)
            (root / path).chmod(0o644)
        files[name] = capture_source(root)
    preserve = flow(
        "preserve",
        [
            step("click", selector={"strategy": "role", "value": "link", "name": "Continue"}),
            step(
                "expect-text",
                selector={"strategy": "css", "value": "h1", "name": None},
                value="Next",
            ),
        ],
    )
    target = flow(
        "target",
        [
            step(
                "expect-text",
                selector={"strategy": "css", "value": "h1", "name": None},
                value="New",
            )
        ],
    )
    plan = {
        "format": "verified-evaluator/1",
        "environment_path": "environment/environment.json",
        "criteria_paths": [
            "criteria/execution.json",
            "criteria/preserve.json",
            "criteria/target.json",
            "criteria/tests.json",
        ],
        "environment_paths": ["environment/environment.json"],
        "preview_argv": ["node", "serve.cjs", "{port}"],
        "frozen_time": settings.frozen_time,
        "browser_executable": settings.executable_path,
        "visual_references": [],
    }
    payloads = {
        "criteria/execution.json": canonical_json(plan),
        "criteria/preserve.json": preserve,
        "criteria/target.json": target,
        "criteria/tests.json": b"{}",
        "environment/environment.json": canonical_json(settings.environment),
        **{file.path: file.content for file in files["baseline"].files},
    }
    case.update(
        request="Change the heading to New and preserve navigation.",
        scope_paths=["index.html"],
        assurance_required="trusted-local",
        baseline_tree_sha256=files["baseline"].tree_sha256,
        inputs=[],
        checks=[],
        requirements=[],
    )
    for path, payload in payloads.items():
        role = (
            "criteria"
            if path.startswith("criteria/")
            else "environment"
            if path.startswith("environment/")
            else "source"
        )
        case["inputs"].append({**fixed_file(path, payload).manifest_entry(), "role": role})
    for role, key in [("criteria", "evaluator_sha256"), ("environment", "environment_sha256")]:
        case[key] = manifest_digest(
            fixed_file(item["path"], payloads[item["path"]])
            for item in case["inputs"]
            if item["role"] == role
        )
    for name, role, kind in [
        ("tests", "preserve", "test"),
        ("preserve", "preserve", "browser"),
        ("target", "target", "browser"),
    ]:
        definition_path = f"criteria/{name}.json"
        case["checks"].append(
            {
                "check_id": name,
                "role": role,
                "required": True,
                "kind": kind,
                "definition_path": definition_path,
                "definition_sha256": hashlib.sha256(payloads[definition_path]).hexdigest(),
                "command_argv": [
                    "node",
                    "-e",
                    "console.log(JSON.stringify({executed_count:1,failed_count:0,skipped_count:0}))",
                ]
                if kind == "test"
                else [],
                "viewport": {"width": 320, "height": 200} if kind == "browser" else None,
                "timeout_ms": 15000,
            }
        )
        case["requirements"].append(
            {"requirement_id": name, "description": name, "required": True, "check_ids": [name]}
        )
    store = VerifiedChangeStore(tmp_path / "records")
    store.publish_case(case, payloads)
    return case, store, files


@pytest.mark.parametrize("candidate", ["ready", "regression", "spoofed"])
async def test_real_engine_evaluator_observes_both_versions_and_rejects_regression(
    tmp_path, settings, candidate, monkeypatch
):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    case, store, before = scenario(tmp_path, settings, candidate)
    record = await VerifiedChangeEngine(
        store, VerifiedEvaluator(trusted_local_approved=True)
    ).verify(
        case["case_id"],
        baseline=tmp_path / "baseline",
        candidate=tmp_path / "candidate",
        run_id=RUN_ID,
        change_requirements={"index.html": ["target"]},
    )
    assert record["decision"] == ("ready" if candidate == "ready" else "blocked"), record["actions"]
    assert record["model_calls"] == []
    assert record["assurance"] == "trusted-local"
    assert record["integrity"]["cleanup_complete"]
    assert record["environment_sha256"] != record_digest(settings.environment)
    assert {result["phase"] for result in record["results"]} == {"baseline", "candidate"}
    assert all(
        result["status"] == "passed" and result["evidence_origin"] == "project-report"
        for result in record["results"]
        if result["check_id"] == "tests"
    )
    for name, snapshot in before.items():
        assert capture_source(tmp_path / name).tree_sha256 == snapshot.tree_sha256
    observations = []
    run_dir = store.path_for("run", RUN_ID)
    for artifact in record["artifacts"]:
        payload = (run_dir / artifact["path"]).read_bytes()
        assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]
        if artifact["kind"] == "data":
            observations.append(json.loads(payload))
    assert observations
    assert all(
        item["environment_sha256"] == record_digest(settings.environment) for item in observations
    )
    assert all(item["cleanup_complete"] for item in observations)
    destination = os.environ.get("DDK_FUNCTIONAL_EVIDENCE_DIR")
    if destination:
        import shutil

        output = Path(destination).resolve() / candidate
        output.mkdir(parents=True, exist_ok=True)
        for artifact in record["artifacts"]:
            target = output / artifact["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(run_dir / artifact["path"], target)
        (output / "run.json").write_bytes(canonical_json(record))
        (output / "originals.json").write_bytes(
            canonical_json(
                {
                    name: {
                        "before": snapshot.tree_sha256,
                        "after": capture_source(tmp_path / name).tree_sha256,
                    }
                    for name, snapshot in before.items()
                }
            )
        )


@pytest.mark.parametrize("color", ["red", "blue"])
async def test_real_visual_reference_is_fixed_and_color_changes_fail(tmp_path, settings, color):
    request, original, _ = request_for(tmp_path, kind="visual", argv=[])
    (original / "serve.cjs").write_bytes(SERVER)
    (original / "index.html").write_text(
        "<!doctype html><link rel='icon' href='data:,'>"
        f"<style>html,body{{margin:0;width:100%;height:100%;background:{color}}}</style>"
    )
    before = capture_source(original)
    definition = fixed_file(
        "criteria/check.json",
        flow(
            "check-command",
            [
                step(
                    "snapshot",
                    reference_path="references/approved.png",
                    rgb_tolerance=0,
                    max_mismatch_ppm=0,
                )
            ],
        ),
    )
    reference = fixed_file("references/approved.png", png((255, 0, 0), (320, 200)))
    plan = decode_json(request.frozen_inputs[0].content)
    plan.update(
        preview_argv=["node", "serve.cjs", "{port}"],
        browser_executable=settings.executable_path,
        visual_references=[
            {
                "path": reference.path,
                "viewport": {"width": 320, "height": 200},
                "environment_sha256": record_digest(settings.environment),
                "mask_sha256": None,
            }
        ],
    )
    frozen = (
        fixed_file("criteria/execution.json", canonical_json(plan)),
        definition,
        fixed_file("environment/environment.json", canonical_json(settings.environment)),
        reference,
    )
    request = replace(
        request,
        snapshot=before,
        frozen_inputs=frozen,
        checks=(
            {
                **request.checks[0],
                "viewport": {"width": 320, "height": 200},
                "definition_sha256": definition.sha256,
                "timeout_ms": 15000,
            },
        ),
        input_tree_sha256=before.tree_sha256,
        evaluator_sha256=manifest_digest(frozen[:2]),
        environment_sha256=manifest_digest(frozen[2:3]),
    )
    outcome = await VerifiedEvaluator(trusted_local_approved=True).evaluate(request)
    assert outcome.results[0]["status"] == ("passed" if color == "red" else "failed")
    assert outcome.results[0]["evidence_origin"] == "trusted-observer"
    assert outcome.cleanup_complete
    assert any(item.kind == "screenshot" for item in outcome.artifacts)
    assert capture_source(original).tree_sha256 == before.tree_sha256
    assert hashlib.sha256(reference.content).hexdigest() == reference.sha256
    destination = os.environ.get("DDK_FUNCTIONAL_EVIDENCE_DIR")
    if destination:
        output = Path(destination).resolve() / ("visual-" + color)
        output.mkdir(parents=True, exist_ok=True)
        for artifact in outcome.artifacts:
            target = output / artifact.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(artifact.content)
        (output / "result.json").write_bytes(
            canonical_json(
                {
                    "results": list(outcome.results),
                    "artifacts": [item.record() for item in outcome.artifacts],
                    "assurance": outcome.assurance,
                    "cleanup_complete": outcome.cleanup_complete,
                    "environment_sha256": outcome.environment_sha256,
                    "browser_environment_sha256": record_digest(settings.environment),
                    "original_before_sha256": before.tree_sha256,
                    "original_after_sha256": capture_source(original).tree_sha256,
                    "reference_sha256": reference.sha256,
                }
            )
        )


@pytest.mark.parametrize(
    "fault",
    ["command-source", "preview-source", "output-limit", "timeout-output", "preview-output"],
)
async def test_real_engine_rejects_changed_private_source_and_request_output_overflow(
    tmp_path, settings, fault
):
    case, store, before = scenario(tmp_path, settings)
    payloads = {
        item["path"]: (
            store.path_for("case", case["case_id"]) / "inputs" / item["path"]
        ).read_bytes()
        for item in case["inputs"]
    }
    case = copy.deepcopy(case)
    case["case_id"] = "00000000-0000-4000-8000-000000000062"
    if fault == "command-source":
        case["checks"][0]["command_argv"][-1] = (
            "require('fs').writeFileSync('index.html','changed by command');"
            "console.log(JSON.stringify({executed_count:1,failed_count:0,skipped_count:0}))"
        )
    elif fault == "preview-source":
        plan = decode_json(payloads["criteria/execution.json"])
        launcher = (
            "const f=require('fs');f.writeFileSync('index.html',"
            "f.readFileSync('index.html','utf8').replace('Old','New'));"
            + SERVER.decode().replace("process.argv[2]", "process.argv[1]")
        )
        plan["preview_argv"] = ["node", "-e", launcher, "{port}"]
        payloads["criteria/execution.json"] = canonical_json(plan)
    elif fault == "output-limit":
        case["limits"]["max_output_bytes"] = 1
    elif fault == "timeout-output":
        optional = case["checks"][0]
        optional.update(
            required=False,
            timeout_ms=30,
            command_argv=["node", "-e", "process.stdout.write('partial');setInterval(()=>{},1000)"],
        )
        case["requirements"][0]["required"] = False
        case["checks"] = [*case["checks"][1:], optional]
    else:
        counter = (
            b"const f=require('fs');f.mkdirSync('dist',{recursive:true});"
            b"const count=f.existsSync('dist/count')?Number(f.readFileSync('dist/count')):0;"
            b"f.writeFileSync('dist/count',String(count+1));"
            + "if(count>=2){console.log('한');process.exit(1);}".encode()
            + SERVER
        )
        for name in before:
            (tmp_path / name / "serve.cjs").write_bytes(counter)
            before[name] = capture_source(tmp_path / name)
        payloads["serve.cjs"] = counter
        case["baseline_tree_sha256"] = before["baseline"].tree_sha256
        optional = {
            **case["checks"][1],
            "check_id": "optional",
            "required": False,
            "definition_path": "criteria/optional.json",
        }
        payloads[optional["definition_path"]] = flow("optional", [step("expect-url", value="/")])
        optional["definition_sha256"] = hashlib.sha256(
            payloads[optional["definition_path"]]
        ).hexdigest()
        case["checks"].append(optional)
        case["requirements"].append(
            {
                "requirement_id": "optional",
                "description": "optional",
                "required": False,
                "check_ids": ["optional"],
            }
        )
        case["inputs"].append(
            {
                **fixed_file(
                    optional["definition_path"], payloads[optional["definition_path"]]
                ).manifest_entry(),
                "role": "criteria",
            }
        )
        plan = decode_json(payloads["criteria/execution.json"])
        plan["criteria_paths"].append(optional["definition_path"])
        payloads["criteria/execution.json"] = canonical_json(plan)
        case["limits"]["max_output_bytes"] = 1
        case["checks"][0].update(kind="command", command_argv=["node", "-e", "process.exit(0)"])
    for item in case["inputs"]:
        payload = payloads[item["path"]]
        item.update(sha256=hashlib.sha256(payload).hexdigest(), size_bytes=len(payload))
    case["evaluator_sha256"] = manifest_digest(
        fixed_file(item["path"], payloads[item["path"]])
        for item in case["inputs"]
        if item["role"] == "criteria"
    )
    store.publish_case(case, payloads)
    record = await VerifiedChangeEngine(
        store, VerifiedEvaluator(trusted_local_approved=True)
    ).verify(
        case["case_id"],
        baseline=tmp_path / "baseline",
        candidate=tmp_path / "candidate",
        run_id=RUN_ID,
        change_requirements={"index.html": ["target"]},
    )
    assert record["decision"] == "blocked"
    assert {item["phase"] for item in record["results"]} == {"baseline"}
    assert record["model_calls"] == []
    assert record["integrity"]["cleanup_complete"]
    reason = (
        "timeout"
        if fault == "timeout-output"
        else "preview server exited"
        if fault == "preview-output"
        else "output_limit"
        if fault == "output-limit"
        else "source_changed"
    )
    assert any(reason in (item["reason_code"] or "") for item in record["results"])
    assert any(
        item["code"]
        == (
            "output_limit"
            if fault in {"output-limit", "timeout-output", "preview-output"}
            else "candidate_mismatch"
        )
        for item in record["actions"]
    )
    run_dir = store.path_for("run", RUN_ID)
    observations = [
        json.loads((run_dir / item["path"]).read_bytes())
        for item in record["artifacts"]
        if item["kind"] == "data"
    ]
    if fault == "preview-source":
        assert observations and all(item["errors"] == [] for item in observations)
        assert any(item["steps"] == ["click", "expect-text"] for item in observations)
    elif fault == "timeout-output":
        assert observations
        assert record["results"][-1]["reason_code"] == "timeout"
    elif fault == "preview-output":
        assert observations
        assert "preview server exited" in record["results"][-1]["reason_code"]
    else:
        assert not observations
    originals = {
        name: {"before": snapshot.tree_sha256, "after": capture_source(tmp_path / name).tree_sha256}
        for name, snapshot in before.items()
    }
    assert all(item["before"] == item["after"] for item in originals.values())
    destination = os.environ.get("DDK_FUNCTIONAL_EVIDENCE_DIR")
    if destination:
        output = Path(destination).resolve() / fault
        output.mkdir(parents=True, exist_ok=True)
        for artifact in record["artifacts"]:
            target = output / artifact["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((run_dir / artifact["path"]).read_bytes())
        (output / "run.json").write_bytes(canonical_json(record))
        (output / "originals.json").write_bytes(canonical_json(originals))

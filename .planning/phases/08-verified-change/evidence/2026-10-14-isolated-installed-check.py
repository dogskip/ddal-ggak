"""Run with the separately installed wheel and Python -I from outside the checkout."""

import asyncio
import hashlib
import json
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import ddk
from ddk.adapters.build_runner import BuildResult
from ddk.adapters.isolated_evaluator import _ENTRY, _NODE_ENV, write_worker_bundle
from ddk.adapters.verified_evaluator import VerifiedEvaluator
from ddk.adapters.verified_isolation import POLICY_SHA256, IsolationRequest, LocalDockerIsolation
from ddk.cli import app
from ddk.models.verified_change import canonical_json, decode_json, record_digest
from ddk.server import mcp
from ddk.services.source_snapshot import SnapshotFile, capture_source, manifest_digest
from ddk.services.verified_change_engine import EvaluationRequest
from typer.main import get_command

SOURCE = Path('/Users/bjchoi/.codex/worktrees/b48f/ddalggak')
DIST = Path('/tmp/ddk-isolated-final-dist')
OUTPUT = SOURCE / '.planning/phases/08-verified-change/evidence/2026-10-14-isolated-installed-final.json'
APP = 'sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c'
CHECKER = 'sha256:56753233a98626af7856fc3f3296b2953172aa810bd1d4f2b8e28c2493d03b50'


def fixed(name, content):
    return SnapshotFile(name, content, hashlib.sha256(content).hexdigest(), 0o644, len(content))


async def main():
    installed = Path(ddk.__file__).resolve().parent
    assert installed.is_relative_to(Path('/tmp/ddk-isolated-installed').resolve()), installed
    wheel = next(DIST.glob('*.whl'))
    sdist = next(DIST.glob('*.tar.gz'))
    compared = 0
    with zipfile.ZipFile(wheel) as archive:
        for source in (SOURCE / 'src/ddk').rglob('*.py'):
            relative = source.relative_to(SOURCE / 'src')
            assert source.read_bytes() == archive.read(str(relative))
            assert source.read_bytes() == (installed.parent / relative).read_bytes()
            compared += 1
        for name in ['chromium-seccomp.json', 'LICENSE-moby']:
            relative = 'assets/verified-change/' + name
            assert archive.read('ddk/' + relative) == (installed / relative).read_bytes()
        assert archive.read('ddk/assets/verified-change/contract.schema.json') == (SOURCE / 'docs/design/verified-change/contract.schema.json').read_bytes()
    command = get_command(app)
    assert set(command.commands['change'].commands) == {'verify', 'status', 'export', 'apply', 'recover'}
    tools = sorted(tool.name for tool in await mcp.list_tools())
    assert tools == ['ddk_status', 'ddk_verify', 'ddk_version', 'design_new', 'preflight']
    with tempfile.TemporaryDirectory(prefix='ddk-installed-probe-') as folder:
        root = Path(folder).resolve()
        for name in ['app', 'criteria', 'results']:
            (root / name).mkdir()
        bundle = write_worker_bundle(root / 'criteria')
        isolation = LocalDockerIsolation()
        availability = await isolation.preflight()

        async def operation(session):
            checker = await session.checker(_ENTRY, timeout_s=20, stdin=canonical_json({'mode': 'probe', 'browser_executable': None}))
            app = await session.app(('node', '-e', _NODE_ENV, 'npm'), timeout_s=5)
            assert checker.success and app.success, (checker, app)
            return BuildResult(True, canonical_json({**decode_json(checker.stdout.encode()), **decode_json(app.stdout.encode())}).decode(), '', 0)

        answer = await isolation.execute(IsolationRequest(root, root/'app', root/'criteria', root/'results', APP, CHECKER, ('node', '-e', 'setInterval(()=>{},1000)'), _ENTRY, timeout_s=40), b'', operation=operation)
        assert answer.completed and answer.cleanup_complete, answer
        examples = json.loads((SOURCE / 'docs/design/verified-change/contract-examples.json').read_text())
        env = next(item['record'] for item in examples['valid'] if item['record'].get('record_type') == 'environment')
        env.update(decode_json(answer.stdout.encode()), assurance='isolated', endpoint_kind='local', runtime_name='docker', runtime_version=availability.runtime_version, app_image_sha256=APP.removeprefix('sha256:'), checker_image_sha256=CHECKER.removeprefix('sha256:'), package_manager='npm', lockfile_sha256=hashlib.sha256(b'{}').hexdigest(), policy_sha256=POLICY_SHA256, locale='en-US', timezone='UTC')
        (root/'app/index.html').write_text('<h1>Installed</h1>')
        (root/'app/package-lock.json').write_bytes(b'{}')
        snapshot = capture_source(root/'app')
        definition = fixed('criteria/check.json', b'{}')
        plan = {'format':'verified-evaluator/1', 'environment_path':'environment/environment.json', 'criteria_paths':['criteria/execution.json', definition.path], 'environment_paths':['environment/environment.json'], 'preview_argv':[], 'frozen_time':'2026-10-14T00:00:00+00:00', 'browser_executable':None, 'visual_references':[]}
        frozen = (fixed('criteria/execution.json',canonical_json(plan)),definition,fixed('environment/environment.json',canonical_json(env)))
        check = {'check_id':'installed-command', 'role':'preserve', 'required':True, 'kind':'command', 'definition_path':definition.path, 'definition_sha256':definition.sha256, 'command_argv':['node','-e',"console.log('installed-isolated')"], 'viewport':None, 'timeout_ms':20000}
        request = EvaluationRequest('00000000-0000-4000-8000-000000000001',(check,),'candidate',snapshot,frozen,manifest_digest(frozen[2:]),manifest_digest(frozen[:2]),snapshot.tree_sha256,time.monotonic_ns()+40_000_000_000,lambda:False,{'max_file_bytes':2*1024**2,'max_artifact_bytes':200*1024**2,'max_output_bytes':10*1024**2,'cleanup_timeout_ms':10000,'step_timeout_ms':30000})
        outcome = await VerifiedEvaluator().evaluate(request)
        assert outcome.assurance == 'isolated' and outcome.cleanup_complete, outcome
        assert outcome.results[0]['status'] == 'passed', outcome
        assert capture_source(root/'app').tree_sha256 == snapshot.tree_sha256
        report = {'checked_at':datetime.now(UTC).isoformat(), 'result':'passed', 'cwd':str(Path.cwd()), 'installed_package':str(installed), 'python_modules_compared':compared, 'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(), 'sdist_sha256':hashlib.sha256(sdist.read_bytes()).hexdigest(), 'worker_bundle_sha256':bundle, 'installed_cli_commands':5, 'installed_mcp_tools':tools, 'actual_isolated_command':outcome.results[0], 'cleanup_complete':outcome.cleanup_complete, 'original_preserved':True, 'environment':env, 'policy_evidence':answer.evidence, 'scope':'installed imports, CLI/MCP registration, byte equality and actual isolated command; browser scenarios use the source-checkout E2E evidence'}
        OUTPUT.write_bytes(canonical_json(report)+b'\n')
        print(json.dumps({'result':'passed','python_modules_compared':compared,'installed_package':str(installed),'actual_isolated_command':'passed','cleanup_complete':True}))


asyncio.run(main())

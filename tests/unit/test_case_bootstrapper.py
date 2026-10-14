from __future__ import annotations

import subprocess

from ddk.services.case_bootstrapper import CaseBootstrapper
from ddk.services.verified_change_store import VerifiedChangeStore
from tests.unit.adapters.test_verified_browser import environment


def setup_repo(path):
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for k, v in [("user.name", "Test"), ("user.email", "test@example.invalid")]:
        subprocess.run(["git", "-C", str(path), "config", k, v], check=True)
    (path / "index.html").write_text("<h1>Before</h1>")
    subprocess.run(["git", "-C", str(path), "add", "index.html"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "initial"], check=True)


async def test_bootstrap_requires_no_manual_hashes_and_seals_all_inputs(tmp_path):
    setup_repo(tmp_path)
    config = {
        "preview_argv": ["python3", "-m", "http.server", "{port}", "--bind", "127.0.0.1"],
        "scope_paths": ["index.html"],
        "checks": [
            {
                "check_id": "target",
                "role": "target",
                "steps": [{"action": "expect-text", "selector": "h1", "value": "After"}],
            },
            {
                "check_id": "preserve",
                "role": "preserve",
                "steps": [{"action": "expect-visible", "selector": "body"}],
            },
        ],
    }
    env = environment()
    env["assurance"] = "trusted-local"
    boot = CaseBootstrapper(tmp_path)
    case = await boot.initialize(
        "Heading changes", configuration=config, observed_environment=(env, None)
    )
    stored = VerifiedChangeStore(tmp_path, create=False).case(case["case_id"])
    assert stored == case and len(case["checks"]) == 2
    assert all(len(item["sha256"]) == 64 for item in case["inputs"])
    assert case["source_origin"] == "git_ref"


async def test_no_acceptance_definition_is_explicitly_blocked_and_dry_run_does_not_write(tmp_path):
    setup_repo(tmp_path)
    result = await CaseBootstrapper(tmp_path).initialize("Implement login", dry_run=True)
    assert result["status"] == "blocked"
    assert result["actions"][0]["code"] == "acceptance_checks_required"
    assert not (tmp_path / ".ddk").exists()

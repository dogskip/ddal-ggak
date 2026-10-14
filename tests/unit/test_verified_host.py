from __future__ import annotations

import json

import pytest

from ddk.services import verified_host


@pytest.fixture
def observed_tools(monkeypatch):
    async def environment(repository):
        return {"browser_binary_sha256": "a" * 64, "font_manifest_sha256": "b" * 64}, "browser"

    monkeypatch.setattr(
        verified_host, "tool_version", lambda argv: "" if "status" in argv else "v1"
    )
    monkeypatch.setattr(verified_host, "observe_environment", environment)
    monkeypatch.setattr(verified_host, "observe_tools", lambda repo: {"docker_images": []})


@pytest.mark.usefixtures("observed_tools")
async def test_readiness_reports_invalid_settings_without_exposing_values(tmp_path, monkeypatch):
    monkeypatch.setenv("DDK_SSIM_THRESHOLD", "5")
    monkeypatch.setenv("DDK_ANTHROPIC_API_KEY", "sk-ant-private-test")
    result = await verified_host.readiness(tmp_path)
    assert result["status"] == "blocked"
    assert any(c["name"] == "settings" and c["status"] == "blocked" for c in result["checks"])
    assert "sk-ant-private-test" not in json.dumps(result)


@pytest.mark.usefixtures("observed_tools")
async def test_readiness_observes_repository_dotenv_without_returning_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("DDK_ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    (tmp_path / ".env").write_text("DDK_ANTHROPIC_API_KEY=sk-ant-repository-test\n")
    result = await verified_host.readiness(tmp_path)
    assert (
        next(c for c in result["checks"] if c["name"] == "provider-credentials")["status"]
        == "ready"
    )
    assert "sk-ant-repository-test" not in json.dumps(result)

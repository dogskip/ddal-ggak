"""Runtime services wired to scripted model replies, for CLI tests that skip the network."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from ddk.adapters.build_runner import BuildResult
from ddk.adapters.filesystem import FilesystemAdapter
from ddk.adapters.screenshot_diff import SSIMResult
from ddk.services.pipeline_runner import RuntimeServices

from .fake_llm_adapter import FakeLLMAdapter
from .fake_playwright_adapter import FakePlaywrightAdapter
from .fake_sandbox import TempDirSandbox

_INTENT_GRAPH_RESPONSE = json.dumps(
    {
        "layout_regions": [],
        "components": [],
        "interactions": [],
        "unresolved_items": [],
        "confidence": 0.9,
    }
)

_DESIGN_SYSTEM_RESPONSE = json.dumps(
    {
        "inferred_tokens": [],
        "primitive_components": ["Button"],
        "token_source": "llm",
    }
)

_GENERATION_PLAN_RESPONSE = json.dumps(
    {
        "nodes": [
            {
                "id": "node-btn",
                "node_type": "component",
                "target_path": "src/components/Button.tsx",
                "dependencies": [],
                "validation_hooks": [],
                "repair_hooks": [],
            }
        ],
        "execution_order": ["node-btn"],
        "target_files": ["src/components/Button.tsx"],
        "validation_hooks": [],
        "estimated_node_count": 1,
    }
)

_GENERATED_NODE_RESPONSE = json.dumps(
    {
        "files": [
            {
                "path": "src/components/Button.tsx",
                "content": "export const Button = () => <button>Click</button>;",
                "language": "typescript",
                "source_node_id": "node-btn",
                "is_new": True,
            }
        ],
        "entry_point": "src/components/Button.tsx",
        "component_exports": ["Button"],
    }
)

_NORMALIZATION_RESPONSE = json.dumps(
    {
        "convention_fixes": [],
        "unresolved_drift": [],
        "patched_files": {},
    }
)


def stub_runtime_services() -> RuntimeServices:
    fake_llm = FakeLLMAdapter(
        responses={
            "you": _INTENT_GRAPH_RESPONSE,
            "analyze": _DESIGN_SYSTEM_RESPONSE,
            "senior": _GENERATION_PLAN_RESPONSE,
            "generate": _GENERATED_NODE_RESPONSE,
            "normalize": _NORMALIZATION_RESPONSE,
        }
    )
    git_stub = MagicMock()
    git_stub.status = MagicMock(return_value={})
    git_stub.diff = MagicMock(return_value="")
    git_stub.log = MagicMock(return_value=[])
    git_stub.create_worktree = AsyncMock()
    git_stub.remove_worktree = AsyncMock()
    git_stub.create_checkpoint = AsyncMock(return_value="fake-checkpoint")
    git_stub.rollback_to = AsyncMock()

    build_stub = MagicMock()
    build_stub.run = AsyncMock(
        return_value=BuildResult(success=True, stdout="", stderr="", returncode=0)
    )

    ss_stub = MagicMock()
    ss_stub.compute_ssim = MagicMock(return_value=SSIMResult(score=1.0, mismatch_regions=[]))
    ss_stub.generate_diff_image = MagicMock(return_value=Path("/tmp/diff.png"))

    return RuntimeServices(
        llm=fake_llm,
        filesystem=FilesystemAdapter(),
        git=git_stub,
        sandbox=TempDirSandbox(),
        build_runner=build_stub,
        browser=FakePlaywrightAdapter(),
        screenshot_diff=ss_stub,
    )

"""Test doubles for ddalggak adapters."""

from .fake_build_runner import FakeBuildRunner, ScriptedBuildRunner
from .fake_cost_tracker import FakeCostTracker
from .fake_fallback_chain import FakeFallbackChain
from .fake_filesystem import InMemoryFilesystem
from .fake_llm_adapter import FakeLLMAdapter
from .fake_playwright_adapter import FakePlaywrightAdapter, PaintingBrowser
from .fake_preview import FakePreviewLauncher
from .fake_rollback import FakeRollbackController
from .fake_sandbox import ProjectSandbox, TempDirSandbox
from .fake_ssim_adapter import FakeSSIMAdapter
from .fake_subprocess import FakeSubprocessRunner

__all__ = [
    "FakeBuildRunner",
    "FakeCostTracker",
    "FakeFallbackChain",
    "FakeLLMAdapter",
    "InMemoryFilesystem",
    "TempDirSandbox",
    "FakeSubprocessRunner",
    "ProjectSandbox",
    "ScriptedBuildRunner",
    "FakePlaywrightAdapter",
    "FakePreviewLauncher",
    "PaintingBrowser",
    "FakeRollbackController",
    "FakeSSIMAdapter",
]

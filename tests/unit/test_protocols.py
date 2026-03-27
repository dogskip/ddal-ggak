"""Protocol conformance tests for all 7 adapters — INFRA-03."""

from ddk.adapters.build_runner import BuildRunner
from ddk.adapters.filesystem import FilesystemAdapter, FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.llm.base import LLMAdapter
from ddk.adapters.playwright_browser import PlaywrightAdapter
from ddk.adapters.sandbox.base import SandboxAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter


class TestProtocolsAreRuntimeCheckable:
    def test_llm_adapter_is_protocol(self):
        assert hasattr(LLMAdapter, "__protocol_attrs__") or hasattr(
            LLMAdapter, "_is_protocol"
        )

    def test_filesystem_port_is_protocol(self):
        assert hasattr(FilesystemPort, "__protocol_attrs__") or hasattr(
            FilesystemPort, "_is_protocol"
        )

    def test_git_adapter_is_protocol(self):
        assert hasattr(GitAdapter, "__protocol_attrs__") or hasattr(
            GitAdapter, "_is_protocol"
        )

    def test_sandbox_adapter_is_protocol(self):
        assert hasattr(SandboxAdapter, "__protocol_attrs__") or hasattr(
            SandboxAdapter, "_is_protocol"
        )

    def test_build_runner_is_protocol(self):
        assert hasattr(BuildRunner, "__protocol_attrs__") or hasattr(
            BuildRunner, "_is_protocol"
        )

    def test_playwright_adapter_is_protocol(self):
        assert hasattr(PlaywrightAdapter, "__protocol_attrs__") or hasattr(
            PlaywrightAdapter, "_is_protocol"
        )

    def test_screenshot_diff_adapter_is_protocol(self):
        assert hasattr(ScreenshotDiffAdapter, "__protocol_attrs__") or hasattr(
            ScreenshotDiffAdapter, "_is_protocol"
        )


class TestFilesystemAdapterConformance:
    def test_satisfies_protocol(self):
        adapter = FilesystemAdapter()
        assert isinstance(adapter, FilesystemPort)

    def test_read_write_roundtrip(self, tmp_path):
        adapter = FilesystemAdapter()
        test_file = tmp_path / "test.txt"
        adapter.write_text(test_file, "hello world")
        assert adapter.read_text(test_file) == "hello world"

    def test_exists(self, tmp_path):
        adapter = FilesystemAdapter()
        assert adapter.exists(tmp_path) is True
        assert adapter.exists(tmp_path / "nonexistent") is False

    def test_list_dir(self, tmp_path):
        adapter = FilesystemAdapter()
        (tmp_path / "a.txt").touch()
        (tmp_path / "b.txt").touch()
        result = adapter.list_dir(tmp_path)
        assert len(result) == 2

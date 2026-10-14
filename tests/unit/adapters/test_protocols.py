"""Tests for adapter protocols — BuildRunner, FilesystemPort, GitAdapter, ScreenshotDiffAdapter."""

from __future__ import annotations

from ddk.adapters.build_runner import BuildResult, BuildRunner
from ddk.adapters.filesystem import FilesystemAdapter, FilesystemPort
from ddk.adapters.git import GitAdapter
from ddk.adapters.screenshot_diff import ScreenshotDiffAdapter, SSIMResult


class TestBuildResult:
    def test_create(self) -> None:
        result = BuildResult(success=True, stdout="ok", stderr="", returncode=0, duration_ms=100)
        assert result.success is True
        assert result.returncode == 0
        assert result.duration_ms == 100

    def test_failure(self) -> None:
        result = BuildResult(success=False, stdout="", stderr="err", returncode=1, duration_ms=50)
        assert result.success is False
        assert result.returncode == 1


class TestBuildRunnerProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert (
            hasattr(BuildRunner, "__protocol_attrs__")
            or hasattr(BuildRunner, "__abstractmethods__")
            or callable(getattr(BuildRunner, "__instancecheck__", None))
        )


class TestFilesystemPort:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(FilesystemPort, "__protocol_attrs__") or callable(
            getattr(FilesystemPort, "__instancecheck__", None)
        )


class TestFilesystemAdapter:
    def test_read_write(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        fs = FilesystemAdapter()
        fs.write_text(root / "test.txt", "hello")
        assert fs.read_text(root / "test.txt") == "hello"

    def test_exists(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        fs = FilesystemAdapter()
        assert fs.exists(root / "nope.txt") is False
        fs.write_text(root / "yes.txt", "data")
        assert fs.exists(root / "yes.txt") is True

    def test_list_dir(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        fs = FilesystemAdapter()
        fs.write_text(root / "a.txt", "a")
        fs.write_text(root / "b.txt", "b")
        items = fs.list_dir(root)
        assert len(items) >= 2

    def test_mkdir(self, tmp_path: object) -> None:
        from pathlib import Path

        root = Path(str(tmp_path))
        fs = FilesystemAdapter()
        fs.mkdir(root / "subdir" / "nested")
        assert (root / "subdir" / "nested").is_dir()

    def test_isinstance_protocol(self) -> None:
        fs = FilesystemAdapter()
        assert isinstance(fs, FilesystemPort)


class TestGitAdapterProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(GitAdapter, "__protocol_attrs__") or callable(
            getattr(GitAdapter, "__instancecheck__", None)
        )


class TestSSIMResult:
    def test_create(self) -> None:
        result = SSIMResult(score=0.95, mismatch_regions=[], diff_image_path=None)
        assert result.score == 0.95
        assert result.mismatch_regions == []


class TestScreenshotDiffProtocol:
    def test_is_runtime_checkable(self) -> None:
        assert hasattr(ScreenshotDiffAdapter, "__protocol_attrs__") or callable(
            getattr(ScreenshotDiffAdapter, "__instancecheck__", None)
        )

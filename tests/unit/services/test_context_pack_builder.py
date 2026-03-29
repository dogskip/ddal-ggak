"""Unit tests for ContextPackBuilder (CODEGEN-03).

Tests verify:
- sort_key priority order (P1 before P5)
- MAX_FILES=6 cap
- MAX_LINES=300 cap
- Tie-break by normalized_path (lexicographic)
- Deterministic hash (same input → same hash)
- Deterministic chunks (same input → identical output)
- insufficient_context=True when no P1 files
- insufficient_context=False when P1 exists
- node_modules excluded
- Binary files excluded
- line_bucket = ceil(lines / 50) used in sort_key
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ddk.models.context_pack import ContextPack
from ddk.services.context_pack_builder import ContextPackBuilder


def _write_lines(path: Path, lines: int, content_prefix: str = "x") -> None:
    """Write a file with exactly `lines` lines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join([f"{content_prefix}{i}" for i in range(lines)]))


@pytest.fixture
def basic_repo(tmp_path: Path) -> Path:
    """Minimal repo with one file of each priority tier."""
    # P1: entry point
    (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')
    # P2: tsconfig
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}}')
    # P3: source component
    src = tmp_path / "src"
    src.mkdir()
    (src / "App.tsx").write_text(
        "import React from 'react';\n"
        "export default function App() { return <div/>; }"
    )
    (src / "components").mkdir()
    (src / "components" / "Button.tsx").write_text(
        "export function Button() { return <button>Click</button>; }"
    )
    # P4: CSS
    (src / "styles").mkdir()
    (src / "styles" / "main.css").write_text("body { margin: 0; }")
    # P5: README
    (tmp_path / "README.md").write_text("# Test Project\n\nDescription here.")
    return tmp_path


@pytest.fixture
def builder() -> ContextPackBuilder:
    return ContextPackBuilder()


class TestSortOrder:
    async def test_p1_appears_before_p5(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """P1 files (package.json) appear before P5 files (README.md) in chunks."""
        pack = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        priorities = [c.priority for c in pack.chunks]
        # Find P1 and P5 indices
        p1_indices = [i for i, p in enumerate(priorities) if p == "P1"]
        p5_indices = [i for i, p in enumerate(priorities) if p == "P5"]
        if p1_indices and p5_indices:
            assert max(p1_indices) < min(p5_indices), (
                f"P1 at {p1_indices}, P5 at {p5_indices} — P1 must precede P5"
            )

    async def test_p2_appears_before_p3(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """P2 files appear before P3 files."""
        pack = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        priorities = [c.priority for c in pack.chunks]
        p2_indices = [i for i, p in enumerate(priorities) if p == "P2"]
        p3_indices = [i for i, p in enumerate(priorities) if p == "P3"]
        if p2_indices and p3_indices:
            assert max(p2_indices) < min(p3_indices)

    async def test_tie_break_normalized_path(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """Same priority and same relation rank → lexicographic path order."""
        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        # Create 3 P3 component files — should sort by path
        (src / "Zebra.tsx").write_text("export function Zebra() { return <div/>; }")
        (src / "Alpha.tsx").write_text("export function Alpha() { return <div/>; }")
        (src / "Mango.tsx").write_text("export function Mango() { return <div/>; }")

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=tmp_path,
        )
        # Filter to same-priority chunks and check path order
        component_chunks = [
            c for c in pack.chunks
            if c.path.endswith(".tsx") and c.path.startswith("src/components/")
        ]
        paths = [c.path for c in component_chunks]
        assert paths == sorted(paths), f"Paths not sorted: {paths}"


class TestBudgetEnforcement:
    async def test_max_files_six(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """Even with 10+ candidates, output has ≤ 6 chunks."""
        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        for i in range(12):
            (src / f"Component{i}.tsx").write_text(
                f"export function C{i}() {{ return <div/>; }}"
            )
        (tmp_path / "package.json").write_text('{"name":"test"}')
        (tmp_path / "tsconfig.json").write_text("{}")

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=tmp_path,
        )
        assert len(pack.chunks) <= 6

    async def test_max_lines_300(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """Output total_lines ≤ 300."""
        # Create files with many lines
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "package.json").write_text('{"name":"test"}')
        # Write multiple files with 80 lines each (5 files × 80 = 400 lines → over budget)
        for i in range(5):
            _write_lines(src / f"Comp{i}.tsx", 80, f"line{i}_")
        _write_lines(tmp_path / "README.md", 100, "readme_")

        pack = builder.build(
            target_files=["src/NewComp.tsx"],
            repo_path=tmp_path,
        )
        assert pack.total_lines <= 300

    async def test_line_count_consistency(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """total_lines matches sum of chunk (end_line - start_line + 1)."""
        src = tmp_path / "src"
        src.mkdir()
        (tmp_path / "package.json").write_text('{"name":"test"}')
        _write_lines(src / "App.tsx", 30, "app_")

        pack = builder.build(
            target_files=["src/NewComp.tsx"],
            repo_path=tmp_path,
        )
        expected_total = sum(c.end_line - c.start_line + 1 for c in pack.chunks)
        assert pack.total_lines == expected_total


class TestDeterminism:
    async def test_deterministic_hash(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Same input → same context_pack_hash."""
        pack1 = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        pack2 = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        assert pack1.context_pack_hash == pack2.context_pack_hash

    async def test_deterministic_chunks(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Two calls with same input → identical chunk list (paths and priorities)."""
        pack1 = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        pack2 = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        paths1 = [c.path for c in pack1.chunks]
        paths2 = [c.path for c in pack2.chunks]
        assert paths1 == paths2

    async def test_hash_changes_with_different_target(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Different target_files → different hash."""
        pack1 = builder.build(
            target_files=["src/components/NewA.tsx"],
            repo_path=basic_repo,
        )
        pack2 = builder.build(
            target_files=["src/components/NewB.tsx"],
            repo_path=basic_repo,
        )
        assert pack1.context_pack_hash != pack2.context_pack_hash

    async def test_hash_is_16_chars(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """context_pack_hash is a 16-char hex string (SHA256[:16])."""
        pack = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        assert len(pack.context_pack_hash) == 16
        assert all(c in "0123456789abcdef" for c in pack.context_pack_hash)


class TestInsufficientContext:
    async def test_insufficient_context_no_p1_files(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """When no P1 files exist → insufficient_context=True."""
        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        (src / "Button.tsx").write_text("export function Button() { return <button/>; }")
        # Only P3/P4 files, no P1 (no package.json / App.tsx / main.tsx)

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=tmp_path,
        )
        assert pack.insufficient_context is True
        assert len(pack.missing_context_for) > 0

    async def test_insufficient_context_has_p1_files(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """When P1 files exist → insufficient_context=False."""
        pack = builder.build(
            target_files=["src/components/NewComponent.tsx"],
            repo_path=basic_repo,
        )
        assert pack.insufficient_context is False

    async def test_missing_context_for_populated_when_insufficient(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """missing_context_for contains target_files when insufficient."""
        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        (src / "Button.tsx").write_text("button")

        target = ["src/components/New.tsx"]
        pack = builder.build(target_files=target, repo_path=tmp_path)
        assert pack.insufficient_context is True
        assert pack.missing_context_for == target


class TestExclusions:
    async def test_node_modules_excluded(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Files under node_modules/ are never included."""
        nm = basic_repo / "node_modules" / "react"
        nm.mkdir(parents=True)
        (nm / "index.js").write_text("module.exports = {};")

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
        )
        paths = [c.path for c in pack.chunks]
        assert not any("node_modules" in p for p in paths)

    async def test_binary_files_excluded(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Binary files (.png, .jpg) are not included."""
        (basic_repo / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d")
        (basic_repo / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0")

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
        )
        paths = [c.path for c in pack.chunks]
        assert not any(p.endswith((".png", ".jpg")) for p in paths)

    async def test_pycache_excluded(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """__pycache__ directories are excluded."""
        (tmp_path / "package.json").write_text('{"name":"test"}')
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "mod.cpython-312.pyc").write_bytes(b"\x00\x00\x00\x00")

        pack = builder.build(
            target_files=["src/New.tsx"],
            repo_path=tmp_path,
        )
        paths = [c.path for c in pack.chunks]
        assert not any("__pycache__" in p for p in paths)


class TestLineBucket:
    async def test_line_bucket_formula(
        self, builder: ContextPackBuilder, tmp_path: Path
    ) -> None:
        """line_bucket = ceil(line_count / 50) influences sort order.

        A file with 51 lines has bucket=2; a file with 50 lines has bucket=1.
        The smaller-bucket file should appear first (all else equal).
        """
        src = tmp_path / "src" / "components"
        src.mkdir(parents=True)
        # Both are P3 (source tsx), same relation_rank (same dir)
        # "aaa.tsx" sorts before "bbb.tsx" lexicographically
        # Give "aaa" 51 lines (bucket=2) and "bbb" 50 lines (bucket=1)
        # "bbb" should appear before "aaa" because lower bucket = smaller file
        _write_lines(src / "aaa.tsx", 51, "aaa_line_")
        _write_lines(src / "bbb.tsx", 50, "bbb_line_")

        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=tmp_path,
        )
        component_chunks = [
            c for c in pack.chunks
            if c.path in ("src/components/aaa.tsx", "src/components/bbb.tsx")
        ]
        if len(component_chunks) == 2:
            # bbb (bucket=1) should come before aaa (bucket=2)
            paths = [c.path for c in component_chunks]
            assert paths.index("src/components/bbb.tsx") < paths.index("src/components/aaa.tsx"), (
                f"bbb (bucket=1) should precede aaa (bucket=2), got order: {paths}"
            )


class TestModelStructure:
    async def test_returns_context_pack_instance(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """build() returns a ContextPack instance."""
        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
        )
        assert isinstance(pack, ContextPack)

    async def test_node_name_set(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """node_name is set on the ContextPack."""
        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
            node_name="generate",
        )
        assert pack.node_name == "generate"

    async def test_target_files_preserved(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """target_files in ContextPack matches input."""
        targets = ["src/components/NewA.tsx", "src/components/NewB.tsx"]
        pack = builder.build(target_files=targets, repo_path=basic_repo)
        assert pack.target_files == targets

    async def test_chunks_have_content_sha256(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """Each chunk has a non-empty content_sha256."""
        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
        )
        for chunk in pack.chunks:
            assert len(chunk.content_sha256) == 64  # full SHA256 hex
            assert all(c in "0123456789abcdef" for c in chunk.content_sha256)

    async def test_schema_version_default(
        self, builder: ContextPackBuilder, basic_repo: Path
    ) -> None:
        """schema_version defaults to '1.0'."""
        pack = builder.build(
            target_files=["src/components/New.tsx"],
            repo_path=basic_repo,
        )
        assert pack.schema_version == "1.0"

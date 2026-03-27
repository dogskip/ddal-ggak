"""Roundtrip serialization tests for CaseInput and RepoProfile model families."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from ddk.models.input import CaseInput
from ddk.models.repo import (
    DesignTokens,
    FileLayoutRules,
    NamingRules,
    RepoProfile,
)


# ── CaseInput ──────────────────────────────────────────────────────


def _make_case_input(**overrides) -> CaseInput:
    defaults = {
        "case_id": "C-001",
        "image_paths": [Path("design.png")],
        "prompt": "로그인 화면을 만들어주세요",
        "repo_path": Path("/tmp/my-app"),
        "reference_notes": "다크 모드 지원",
        "visual_reference_paths": [Path("ref1.png"), Path("ref2.png")],
        "created_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return CaseInput(**defaults)


def test_case_input_roundtrip():
    original = _make_case_input()
    json_str = original.model_dump_json()
    restored = CaseInput.model_validate_json(json_str)
    assert restored == original


def test_case_input_rejects_empty_images():
    with pytest.raises(ValidationError):
        _make_case_input(image_paths=[])


def test_case_input_rejects_long_prompt():
    with pytest.raises(ValidationError):
        _make_case_input(prompt="x" * 2001)


def test_case_input_rejects_empty_prompt():
    with pytest.raises(ValidationError):
        _make_case_input(prompt="")


def test_case_input_rejects_whitespace_only_prompt():
    with pytest.raises(ValidationError):
        _make_case_input(prompt="   ")


def test_case_input_path_serialization():
    original = _make_case_input(
        image_paths=[Path("a/b.png"), Path("c/d.png")],
        repo_path=Path("/workspace/repo"),
    )
    json_str = original.model_dump_json()
    restored = CaseInput.model_validate_json(json_str)
    assert restored.image_paths == original.image_paths
    assert restored.repo_path == original.repo_path


def test_case_input_max_images():
    paths = [Path(f"img{i}.png") for i in range(5)]
    ci = _make_case_input(image_paths=paths)
    assert len(ci.image_paths) == 5


def test_case_input_rejects_too_many_images():
    paths = [Path(f"img{i}.png") for i in range(6)]
    with pytest.raises(ValidationError):
        _make_case_input(image_paths=paths)


# ── NamingRules ────────────────────────────────────────────────────


def test_naming_rules_roundtrip():
    nr = NamingRules()
    json_str = nr.model_dump_json()
    restored = NamingRules.model_validate_json(json_str)
    assert restored == nr


def test_naming_rules_defaults():
    nr = NamingRules()
    assert nr.component_pattern == "PascalCase"
    assert nr.file_pattern == "kebab-case"
    assert nr.hook_prefix == "use"
    assert nr.test_suffix == ".test"
    assert nr.story_suffix == ".stories"
    assert nr.style_suffix == ".module.css"


# ── FileLayoutRules ────────────────────────────────────────────────


def test_file_layout_rules_roundtrip():
    flr = FileLayoutRules()
    json_str = flr.model_dump_json()
    restored = FileLayoutRules.model_validate_json(json_str)
    assert restored == flr


def test_file_layout_rules_defaults():
    flr = FileLayoutRules()
    assert flr.components_dir == "src/components"
    assert flr.test_co_location is True


# ── DesignTokens ───────────────────────────────────────────────────


def test_design_tokens_roundtrip():
    dt = DesignTokens(
        colors={"primary": "#3B82F6", "secondary": "#6B7280"},
        spacing={"xs": "0.25rem", "sm": "0.5rem"},
        typography={"heading1": {"size": "2rem", "weight": "700"}},
        breakpoints={"sm": "640px", "md": "768px"},
        border_radius={"sm": "0.25rem", "lg": "0.5rem"},
    )
    json_str = dt.model_dump_json()
    restored = DesignTokens.model_validate_json(json_str)
    assert restored == dt


# ── RepoProfile ────────────────────────────────────────────────────


def test_repo_profile_roundtrip():
    rp = RepoProfile(
        framework="react",
        language="typescript",
        package_manager="pnpm",
        css_approach="tailwind",
        component_library="shadcn/ui",
        test_runner="vitest",
        build_tool="vite",
        node_version="20",
        naming_rules=NamingRules(component_pattern="PascalCase"),
        file_layout=FileLayoutRules(components_dir="src/ui"),
        design_tokens=DesignTokens(
            colors={"primary": "#000"},
            spacing={"md": "1rem"},
        ),
        existing_components=["Button", "Card"],
    )
    json_str = rp.model_dump_json()
    restored = RepoProfile.model_validate_json(json_str)
    assert restored == rp


def test_repo_profile_defaults():
    rp = RepoProfile(framework="react")
    assert rp.language == "typescript"
    assert rp.package_manager == "pnpm"
    assert rp.css_approach == "tailwind"
    assert rp.build_tool == "vite"
    assert isinstance(rp.naming_rules, NamingRules)
    assert isinstance(rp.file_layout, FileLayoutRules)
    assert isinstance(rp.design_tokens, DesignTokens)
    assert rp.existing_components == []

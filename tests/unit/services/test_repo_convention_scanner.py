"""Unit tests for RepoConventionScanner (INGEST-03, D-07)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ddk.services.repo_convention_scanner import RepoConventionScanner
from tests.fakes.fake_llm_adapter import FakeLLMAdapter

# Path to the shared fixture repo
FIXTURE_REPO = Path(__file__).parent.parent.parent / "fixtures" / "repos" / "react-vite-ts"


@pytest.fixture
def scanner() -> RepoConventionScanner:
    return RepoConventionScanner()


@pytest.fixture
def scanner_with_fake_llm() -> RepoConventionScanner:
    fake_llm = FakeLLMAdapter(
        responses={
            "you": json.dumps({"component_pattern": "PascalCase", "file_pattern": "PascalCase"})
        }
    )
    return RepoConventionScanner(llm=fake_llm)


@pytest.fixture
def react_repo(tmp_path: Path) -> Path:
    pkg = {
        "dependencies": {"react": "^18.0.0", "react-dom": "^18.0.0"},
        "devDependencies": {"vite": "^5.0.0", "tailwindcss": "^3.0.0"},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    return tmp_path


@pytest.fixture
def next_repo(tmp_path: Path) -> Path:
    pkg = {
        "dependencies": {"next": "^14.0.0", "react": "^18.0.0"},
        "devDependencies": {},
    }
    (tmp_path / "package.json").write_text(json.dumps(pkg))
    return tmp_path


class TestFrameworkDetection:
    async def test_detect_react_framework(
        self, scanner: RepoConventionScanner, react_repo: Path
    ) -> None:
        profile = await scanner.scan(react_repo)
        assert profile.framework == "react"

    async def test_detect_next_framework(
        self, scanner: RepoConventionScanner, next_repo: Path
    ) -> None:
        profile = await scanner.scan(next_repo)
        assert profile.framework == "next"

    async def test_no_package_json_framework_other(
        self, scanner: RepoConventionScanner, tmp_path: Path
    ) -> None:
        profile = await scanner.scan(tmp_path)
        assert profile.framework == "other"

    async def test_detect_vue_framework(
        self, scanner: RepoConventionScanner, tmp_path: Path
    ) -> None:
        pkg = {"dependencies": {"vue": "^3.0.0"}, "devDependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        profile = await scanner.scan(tmp_path)
        assert profile.framework == "vue"


class TestTypeScriptDetection:
    async def test_parse_tsconfig_strict(
        self, scanner: RepoConventionScanner, tmp_path: Path
    ) -> None:
        pkg = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        tsconfig = {"compilerOptions": {"strict": True, "target": "ES2020"}}
        (tmp_path / "tsconfig.json").write_text(json.dumps(tsconfig))
        profile = await scanner.scan(tmp_path)
        assert profile.language == "typescript"


class TestCSSDetection:
    async def test_detect_tailwind(
        self, scanner: RepoConventionScanner, react_repo: Path
    ) -> None:
        profile = await scanner.scan(react_repo)
        assert profile.css_approach == "tailwind"

    async def test_detect_styled_components(
        self, scanner: RepoConventionScanner, tmp_path: Path
    ) -> None:
        pkg = {
            "dependencies": {"react": "^18.0.0", "styled-components": "^6.0.0"},
            "devDependencies": {},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        profile = await scanner.scan(tmp_path)
        assert profile.css_approach == "styled-components"


class TestPackageManagerDetection:
    async def test_detect_package_manager_pnpm(
        self, scanner: RepoConventionScanner, react_repo: Path
    ) -> None:
        (react_repo / "pnpm-lock.yaml").write_text("lockfileVersion: '6.0'")
        profile = await scanner.scan(react_repo)
        assert profile.package_manager == "pnpm"

    async def test_detect_package_manager_yarn(
        self, scanner: RepoConventionScanner, react_repo: Path
    ) -> None:
        (react_repo / "yarn.lock").write_text("# yarn lockfile v1")
        profile = await scanner.scan(react_repo)
        assert profile.package_manager == "yarn"

    async def test_detect_package_manager_npm(
        self, scanner: RepoConventionScanner, tmp_path: Path
    ) -> None:
        # No lock file → defaults to npm
        pkg = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        profile = await scanner.scan(tmp_path)
        assert profile.package_manager == "npm"


class TestLLMSupplement:
    async def test_llm_supplement_called_when_framework_other(
        self, tmp_path: Path
    ) -> None:
        fake_llm = FakeLLMAdapter(
            responses={
                "you": json.dumps({"component_pattern": "kebab-case", "file_pattern": "kebab-case"})
            }
        )
        scanner = RepoConventionScanner(llm=fake_llm)
        # Empty dir → framework="other" → should trigger LLM
        profile = await scanner.scan(tmp_path)
        assert profile.framework == "other"
        assert len(fake_llm.call_log) == 1  # LLM was called

    async def test_llm_not_called_when_static_sufficient_and_no_llm(
        self, react_repo: Path
    ) -> None:
        # React detected statically, no LLM adapter provided → no LLM call
        scanner = RepoConventionScanner(llm=None)
        profile = await scanner.scan(react_repo)
        assert profile.framework == "react"
        # No exception raised, no LLM call possible

    async def test_llm_not_called_for_react_framework(
        self, react_repo: Path
    ) -> None:
        fake_llm = FakeLLMAdapter(responses={})
        scanner = RepoConventionScanner(llm=fake_llm)
        # react framework detected → no LLM supplement
        profile = await scanner.scan(react_repo)
        assert profile.framework == "react"
        assert len(fake_llm.call_log) == 0  # LLM was NOT called


class TestFixtureRepoScan:
    async def test_fixture_repo_scan(self, scanner: RepoConventionScanner) -> None:
        """Full scan of the react-vite-ts fixture repo."""
        profile = await scanner.scan(FIXTURE_REPO)
        assert profile.framework == "react"
        assert profile.build_tool == "vite"
        assert profile.css_approach == "tailwind"
        assert profile.language == "typescript"


class TestRepoScanNode:
    async def test_repo_scan_node_thin_adapter(self, tmp_path: Path) -> None:
        from ddk.graph.nodes.repo_scan import repo_scan_node
        from ddk.models.input import CaseInput

        pkg = {"dependencies": {"react": "^18.0.0"}, "devDependencies": {}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        case_input = CaseInput(
            case_id="C-001",
            image_paths=[tmp_path / "img.png"],  # we won't call intake so path doesn't matter
            prompt="테스트",
            repo_path=tmp_path,
        )
        # Create a dummy image so CaseInput doesn't fail validation
        (tmp_path / "img.png").write_bytes(b"\x89PNG")

        state = {"case_input": case_input}
        result = await repo_scan_node(state)
        assert result["current_node"] == "repo_scan"
        assert result["repo_profile"].framework == "react"

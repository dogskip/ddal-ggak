# 프로젝트 디렉토리 구조 및 모듈 설계

## 1. 전체 레이아웃

```
ddalggak/
├── pyproject.toml              ← 패키지 정의, 의존성, CLI entrypoint
├── uv.lock
├── README.md
├── CLAUDE.md                   ← 딸깍 프로젝트 AI 지침
│
├── src/
│   └── ddk/
│       ├── __init__.py         ← version = "0.1.0"
│       ├── cli.py              ← Typer app, 모든 서브커맨드 등록
│       ├── mcp_server.py       ← FastMCP server (ddk mcp)
│       ├── install.py          ← ddk install --adapter X
│       │
│       ├── models/             ← Pydantic 계약 (schema)
│       │   ├── __init__.py
│       │   ├── input.py        ← CaseInput
│       │   ├── repo.py         ← RepoProfile, NamingRules, FileLayoutRules, DesignTokens
│       │   ├── intent.py       ← IntentGraph, LayoutRegion, ComponentSpec, InteractionSpec, BoundingBox
│       │   ├── generation.py   ← GenerationPlan, GenerationNode, GeneratedArtifactSet, GeneratedFile
│       │   ├── normalization.py← NormalizationReport, ConventionFix
│       │   ├── validation.py   ← RuntimeValidationReport, FailureRecord
│       │   ├── visual.py       ← VisualRegressionReport, MismatchRegion
│       │   ├── fix.py          ← FixAttempt
│       │   ├── scorecard.py    ← Scorecard
│       │   ├── release.py      ← ReleaseDecision
│       │   ├── llm.py          ← LLMCallRecord
│       │   └── evidence.py     ← EvidencePack
│       │
│       ├── graph/              ← LangGraph state machine
│       │   ├── __init__.py
│       │   ├── state.py        ← GraphState TypedDict 정의
│       │   ├── builder.py      ← StateGraph 생성 함수
│       │   ├── edges.py        ← 조건부 edge 함수들
│       │   └── nodes/
│       │       ├── __init__.py
│       │       ├── ingest.py
│       │       ├── repo_scan.py
│       │       ├── intent_extract.py
│       │       ├── plan.py
│       │       ├── generate.py
│       │       ├── normalize.py
│       │       ├── runtime_validate.py
│       │       ├── visual_regress.py
│       │       ├── auto_fix.py
│       │       ├── benchmark.py
│       │       └── certify.py
│       │
│       ├── services/           ← Domain Services (비즈니스 로직)
│       │   ├── __init__.py
│       │   ├── repo_scanner.py         ← RepoConventionScanner
│       │   ├── intent_extractor.py     ← SemanticIntentExtractor
│       │   ├── design_inferencer.py    ← DesignSystemInferencer
│       │   ├── generation_planner.py   ← GenerationPlanner
│       │   ├── code_generator.py       ← CodeGenerator
│       │   ├── normalizer.py           ← OutputNormalizer
│       │   ├── runtime_validator.py    ← RuntimeValidationAggregator
│       │   ├── visual_regression.py    ← VisualRegressionService
│       │   ├── failure_classifier.py   ← FailureClassifier
│       │   ├── auto_fix_planner.py     ← AutoFixPlanner
│       │   ├── retry_controller.py     ← RetryBudgetController
│       │   ├── context_pack_builder.py ← ContextPackBuilder
│       │   ├── benchmark_service.py    ← BenchmarkScorecardService
│       │   ├── release_decision.py     ← ReleaseDecisionService
│       │   └── evidence_builder.py     ← EvidencePackBuilder
│       │
│       ├── adapters/           ← 외부 시스템 어댑터
│       │   ├── __init__.py
│       │   ├── llm/
│       │   │   ├── __init__.py
│       │   │   ├── base.py             ← LLMAdapter Protocol, Message, LLMResponse, LLMCallConfig
│       │   │   ├── anthropic.py        ← AnthropicAdapter
│       │   │   ├── openai.py           ← OpenAIAdapter
│       │   │   ├── recorder.py         ← LLMCallRecorder
│       │   │   ├── router.py           ← ModelRouter (노드별 모델 선택)
│       │   │   └── cost_tracker.py     ← CostTracker
│       │   ├── filesystem.py           ← FilesystemAdapter
│       │   ├── git.py                  ← GitAdapter
│       │   ├── sandbox/
│       │   │   ├── __init__.py
│       │   │   ├── base.py             ← SandboxAdapter Protocol
│       │   │   ├── worktree.py         ← WorktreeSandbox (기본)
│       │   │   └── policy.py           ← CommandAllowlist, PathPolicy
│       │   ├── build_runner.py         ← BuildRunner (npm run build 등)
│       │   ├── playwright_browser.py   ← PlaywrightAdapter
│       │   ├── screenshot_diff.py      ← ScreenshotDiffAdapter (SSIM)
│       │   └── console_capture.py      ← ConsoleCapture
│       │
│       ├── workspace/          ← 케이스 워크스페이스 관리
│       │   ├── __init__.py
│       │   ├── manager.py              ← WorkspaceManager
│       │   ├── checkpoint.py           ← CheckpointManager
│       │   └── rollback.py             ← RollbackController
│       │
│       ├── preflight/          ← 환경 사전 검사
│       │   ├── __init__.py
│       │   └── doctor.py               ← PreflightDoctor
│       │
│       └── design_studio/      ← ddk design 기능
│           ├── __init__.py
│           ├── interviewer.py          ← RequirementsInterviewer
│           ├── doc_generator.py        ← StandardsDocGenerator
│           └── quality_gate.py         ← DesignQualityGate
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             ← 공통 fixtures
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_retry_budget_controller.py
│   │   ├── test_context_pack_builder.py
│   │   ├── test_context_budget_policy.py
│   │   ├── test_failure_taxonomy_ids.py
│   │   ├── test_visual_diff_scoring.py
│   │   ├── test_release_rule_aggregation.py
│   │   ├── test_checkpoint_policy.py
│   │   ├── test_rollback_rules.py
│   │   ├── test_llm_call_record_schema.py
│   │   ├── test_context_pack_hash.py
│   │   ├── test_preflight_checks.py
│   │   ├── test_remediation_hints.py
│   │   ├── test_cost_tracker.py
│   │   ├── test_model_router.py
│   │   └── test_sandbox_policy.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_init_workspace.py
│   │   ├── test_repo_scan_fixtures.py
│   │   ├── test_runtime_validation_pipeline.py
│   │   ├── test_visual_regression_runner.py
│   │   ├── test_auto_fix_loop.py
│   │   ├── test_sandbox_runner.py
│   │   ├── test_git_checkpoint.py
│   │   ├── test_rollback_integration.py
│   │   ├── test_preflight_doctor_integration.py
│   │   ├── test_mcp_server_design.py
│   │   ├── test_mcp_server_execute.py
│   │   ├── test_install_adapter_claude.py
│   │   ├── test_install_adapter_copilot.py
│   │   ├── test_install_adapter_gemini.py
│   │   ├── test_install_adapter_opencode.py
│   │   └── test_install_adapter_codex.py
│   ├── contract/
│   │   ├── __init__.py
│   │   ├── test_case_input_schema.py
│   │   ├── test_graph_state_schema.py
│   │   ├── test_runtime_validation_schema.py
│   │   ├── test_visual_report_schema.py
│   │   ├── test_scorecard_schema.py
│   │   ├── test_release_decision_schema.py
│   │   ├── test_llm_call_record_contract.py
│   │   ├── test_mcp_server_tools.py
│   │   ├── test_claude_command_files.py
│   │   ├── test_github_skill_files.py
│   │   └── test_extension_json_schema.py
│   └── e2e/
│       ├── __init__.py
│       ├── conftest.py         ← E2E fixtures, fake LLM provider
│       ├── test_generate_basic_e2e.py
│       ├── test_runtime_validate_e2e.py
│       ├── test_visual_gate_e2e.py
│       ├── test_fix_loop_e2e.py
│       ├── test_certify_release_e2e.py
│       └── test_sandbox_block_e2e.py
│
├── templates/                  ← ddk install --adapter X 에 사용되는 템플릿
│   ├── claude-commands/
│   │   └── ddk/
│   │       ├── design.md
│   │       ├── new-project.md
│   │       ├── plan-phase.md
│   │       ├── execute-phase.md
│   │       ├── verify-work.md
│   │       ├── debug.md
│   │       ├── review.md
│   │       ├── ui-gen.md
│   │       ├── visual-check.md
│   │       ├── auto-fix.md
│   │       ├── certify.md
│   │       ├── rollback.md
│   │       ├── ship.md
│   │       ├── preflight.md
│   │       └── benchmark.md
│   ├── copilot-skills/
│   │   ├── ddalggak-design/skill.md
│   │   ├── ddalggak-new-project/skill.md
│   │   ├── ddalggak-plan-phase/skill.md
│   │   ├── ddalggak-execute-phase/skill.md
│   │   ├── ddalggak-debug/skill.md
│   │   ├── ddalggak-review/skill.md
│   │   ├── ddalggak-ui-gen/skill.md
│   │   ├── ddalggak-visual-check/skill.md
│   │   ├── ddalggak-auto-fix/skill.md
│   │   ├── ddalggak-certify/skill.md
│   │   ├── ddalggak-rollback/skill.md
│   │   ├── ddalggak-ship/skill.md
│   │   └── ddalggak-preflight/skill.md
│   ├── copilot-agents/
│   │   ├── ddalggak-designer.md
│   │   ├── ddalggak-executor.md
│   │   ├── ddalggak-debugger.md
│   │   ├── ddalggak-reviewer.md
│   │   └── ddalggak-ui-generator.md
│   ├── gemini-extension/
│   │   └── ddalggak/
│   │       └── extension.json
│   ├── opencode/
│   │   └── opencode.json.tpl
│   ├── codex/
│   │   └── instructions.md
│   └── mcp/
│       └── mcp.json.tpl        ← .mcp.json 템플릿
│
├── fixtures/                   ← 테스트용 고정 데이터
│   ├── repos/
│   │   └── react-vite-ts/      ← P0 테스트 픽스처 repo
│   │       ├── package.json
│   │       ├── vite.config.ts
│   │       ├── tsconfig.json
│   │       └── src/
│   │           ├── App.tsx
│   │           └── components/
│   └── images/
│       ├── dashboard-mockup.png
│       ├── login-mockup.png
│       └── card-component.png
│
├── benchmarks/
│   ├── README.md
│   └── gsd-baseline.json       ← GSD 측정 결과 (실측 후 채움)
│
└── .ddk/                       ← 각 프로젝트에서 생성되는 런타임 폴더 (예시)
    └── README.md               ← .ddk/ 구조 설명
```

---

## 2. 핵심 모듈 책임

### `src/ddk/cli.py`

```python
import typer
from ddk import __version__

app = typer.Typer(
    name="ddk",
    help="딸깍 — AI 코딩 워크플로우 (GSD 완전 호환 + closed feedback loop)",
    no_args_is_help=True,
)

# 서브앱 등록
app.add_typer(design_app, name="design", help="설계 문서 자동 생성")
app.add_typer(workflow_app, name="workflow", help="프로젝트 워크플로우")
app.add_typer(visual_app, name="visual", help="UI 생성 및 시각 검증")
# ... 나머지 서브앱

@app.callback()
def main(version: bool = typer.Option(False, "--version", "-V")):
    if version:
        typer.echo(f"ddk {__version__}")
        raise typer.Exit()
```

### `src/ddk/graph/state.py`

```python
from typing import TypedDict, Optional
from ddk.models import (
    CaseInput, RepoProfile, IntentGraph, GenerationPlan,
    GeneratedArtifactSet, NormalizationReport, RuntimeValidationReport,
    VisualRegressionReport, FixAttempt, Scorecard, ReleaseDecision, EvidencePack
)

class GraphState(TypedDict):
    # Core state
    case_id: str
    case_input: Optional[CaseInput]
    repo_profile: Optional[RepoProfile]
    intent_graph: Optional[IntentGraph]
    generation_plan: Optional[GenerationPlan]
    generated_artifacts: Optional[GeneratedArtifactSet]
    normalization_report: Optional[NormalizationReport]
    runtime_validation_report: Optional[RuntimeValidationReport]
    visual_regression_report: Optional[VisualRegressionReport]
    fix_attempts: list[FixAttempt]
    scorecard: Optional[Scorecard]
    release_decision: Optional[ReleaseDecision]
    evidence_pack: Optional[EvidencePack]

    # Control flow
    retry_budget_remaining: int
    current_node: str
    terminal_state: Optional[str]
    error_message: Optional[str]
    pre_run_checkpoint_ref: Optional[str]  # RollbackController 체크포인트 ref

    # LLM tracking
    llm_call_records: list[str]  # LLMCallRecord artifact refs
    total_cost_usd: float
    reproducibility_seed: Optional[int]    # benchmark 모드에서 고정
```

### `src/ddk/workspace/manager.py`

```python
from pathlib import Path
import json
from datetime import datetime, timezone

SCHEMA_VERSION = "1.0"

class WorkspaceManager:
    """
    .ddk/ 워크스페이스 구조:
    .ddk/
      schema-version.json
      cases/
        C-001/
          input.json
          repo-profile.json
          intent-graph.json
          generation-plan.json
          artifacts/
            src/...
          reports/
            normalization.json
            runtime-validation.json
            visual-regression.json
          fix-attempts/
            attempt-1.json
            attempt-2.json
          scorecard.json
          release-decision.json
          evidence-pack.json
          llm-calls/
            intent_extract-20241201120000.json
            generate-20241201120001.json
    """
    def __init__(self, project_root: Path):
        self.root = project_root / ".ddk"

    def init(self) -> None:
        """Idempotent 초기화."""
        self.root.mkdir(exist_ok=True)
        (self.root / "cases").mkdir(exist_ok=True)
        schema_file = self.root / "schema-version.json"
        if not schema_file.exists():
            schema_file.write_text(json.dumps({"version": SCHEMA_VERSION}))

    def next_case_id(self) -> str:
        """C-001, C-002 순서로 증가."""
        cases = list((self.root / "cases").iterdir())
        n = len([c for c in cases if c.is_dir()]) + 1
        return f"C-{n:03d}"

    def case_dir(self, case_id: str) -> Path:
        return self.root / "cases" / case_id
```

---

## 3. .ddk/ 런타임 폴더 구조

```
프로젝트루트/
└── .ddk/
    ├── schema-version.json          ← {"version": "1.0"}
    └── cases/
        └── C-001/
            ├── input.json           ← CaseInput artifact
            ├── repo-profile.json    ← RepoProfile artifact
            ├── intent-graph.json    ← IntentGraph artifact
            ├── generation-plan.json ← GenerationPlan artifact
            ├── artifacts/           ← 생성된 파일들 (실제 코드)
            │   └── src/
            ├── reports/
            │   ├── normalization.json
            │   ├── runtime-validation.json
            │   └── visual-regression.json
            ├── fix-attempts/
            │   ├── attempt-1.json   ← FixAttempt artifact
            │   └── attempt-2.json
            ├── llm-calls/           ← LLMCallRecord artifacts
            │   ├── intent_extract-....json
            │   └── generate-....json
            ├── screenshots/
            │   ├── reference.png
            │   ├── generated.png
            │   └── diff.png
            ├── scorecard.json
            ├── release-decision.json
            └── evidence-pack.json   ← 전체 요약 + ref 목록
```

---

## 4. pyproject.toml 전체

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ddalggak"
version = "0.1.0"
description = "AI 코딩 워크플로우 — generate → validate → auto-fix closed loop"
readme = "README.md"
requires-python = ">=3.12"
dependencies = [
    "typer[all]>=0.12.0",
    "pydantic>=2.0.0",
    "langgraph>=0.2.0",
    "anthropic>=0.40.0",
    "openai>=1.40.0",
    "mcp>=1.0.0",
    "playwright>=1.40.0",
    "pillow>=10.0.0",
    "scikit-image>=0.22.0",   # SSIM 계산
    "gitpython>=3.1.0",
    "ruff>=0.7.0",
    "pyright>=1.1.380",
    "rich>=13.0.0",           # CLI 출력
    "httpx>=0.27.0",          # 비동기 HTTP
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
]

[project.scripts]
ddk = "ddk.cli:app"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
select = ["E", "F", "I", "N", "UP", "B", "C4", "SIM"]

[tool.pyright]
pythonVersion = "3.12"
typeCheckingMode = "strict"
```

---

## 5. Import 경로 예시

```python
# 모델
from ddk.models.intent import IntentGraph, LayoutRegion, ComponentSpec
from ddk.models.validation import RuntimeValidationReport, FailureRecord
from ddk.models.evidence import EvidencePack

# 서비스
from ddk.services.intent_extractor import SemanticIntentExtractor
from ddk.services.retry_controller import RetryBudgetController

# 어댑터
from ddk.adapters.llm.anthropic import AnthropicAdapter
from ddk.adapters.llm.recorder import LLMCallRecorder
from ddk.adapters.sandbox.worktree import WorktreeSandbox

# 그래프
from ddk.graph.builder import build_generation_graph
from ddk.graph.state import GraphState

# 워크스페이스
from ddk.workspace.manager import WorkspaceManager
from ddk.workspace.checkpoint import CheckpointManager
```

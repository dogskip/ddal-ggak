# GitHub Actions CI Workflow

> `.github/workflows/` 전체 명세.
> 이 파일 없이는 자동화된 merge gate가 없다.

---

## 1. PR 게이트 (`.github/workflows/ci.yml`)

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_VERSION: "3.12"
  UV_CACHE_DIR: ~/.cache/uv

jobs:
  # ─── 1단계: 정적 검사 ───────────────────────────────────────────
  static:
    name: Static Checks
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        run: pip install uv

      - name: Cache uv
        uses: actions/cache@v4
        with:
          path: ${{ env.UV_CACHE_DIR }}
          key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Ruff lint
        run: uv run ruff check src/ tests/

      - name: Ruff format check
        run: uv run ruff format --check src/ tests/

      - name: Pyright type check
        run: uv run pyright src/

  # ─── 2단계: Unit 테스트 ─────────────────────────────────────────
  unit:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: static
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        run: pip install uv

      - name: Cache uv
        uses: actions/cache@v4
        with:
          path: ${{ env.UV_CACHE_DIR }}
          key: uv-${{ runner.os }}-${{ hashFiles('uv.lock') }}

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run unit tests
        run: |
          uv run pytest tests/unit/ \
            -v \
            --tb=short \
            --cov=src/ddk \
            --cov-report=term-missing \
            --cov-report=xml:coverage.xml \
            --cov-fail-under=80
        env:
          DDK_LLM_PROVIDER: fake

      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-unit
          path: coverage.xml

  # ─── 3단계: Integration 테스트 ──────────────────────────────────
  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    needs: unit
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Set up Node.js (sandbox 빌드용)
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install pnpm
        run: npm install -g pnpm

      - name: Run integration tests
        run: |
          uv run pytest tests/integration/ \
            -v \
            --tb=short \
            -x
        env:
          DDK_LLM_PROVIDER: fake
          DDK_SANDBOX_MODE: worktree

      - name: Upload sandbox logs on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: sandbox-logs
          path: /tmp/ddk-sandbox-*/

  # ─── 4단계: Contract 테스트 ────────────────────────────────────
  contract:
    name: Contract Tests
    runs-on: ubuntu-latest
    needs: unit
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run contract tests
        run: |
          uv run pytest tests/contract/ \
            -v \
            --tb=short

  # ─── 5단계: E2E 테스트 (PR merge 시만) ─────────────────────────
  e2e:
    name: E2E Tests
    runs-on: ubuntu-latest
    needs: [integration, contract]
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install pnpm
        run: npm install -g pnpm

      - name: Install Playwright Chromium
        run: uv run playwright install chromium --with-deps

      - name: Install fixture repo dependencies
        run: |
          cd fixtures/repos/react-vite-ts
          pnpm install --frozen-lockfile

      - name: Run E2E tests
        run: |
          uv run pytest tests/e2e/ \
            -v \
            --tb=long \
            --retries=1 \
            --timeout=300
        env:
          DDK_LLM_PROVIDER: fake
          DDK_SANDBOX_MODE: worktree
          DDK_PLAYWRIGHT_BROWSER: chromium

      - name: Upload E2E artifacts on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: e2e-artifacts
          path: |
            .ddk/cases/*/screenshots/
            .ddk/cases/*/reports/
```

---

## 2. Release Workflow (`.github/workflows/release.yml`)

```yaml
# .github/workflows/release.yml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  build-and-publish:
    name: Build & Publish to PyPI
    runs-on: ubuntu-latest
    environment: release
    permissions:
      id-token: write  # OIDC for PyPI trusted publishing
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        run: pip install uv

      - name: Run full test suite
        run: uv run pytest tests/unit/ tests/integration/ tests/contract/ -v

      - name: Build
        run: uv build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

---

## 3. Pre-commit 설정 (`.pre-commit-config.yaml`)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict

  - repo: local
    hooks:
      - id: pyright
        name: Pyright type check
        entry: uv run pyright src/
        language: system
        types: [python]
        pass_filenames: false
```

---

## 4. pytest 설정 (`pyproject.toml` 추가)

```toml
# pyproject.toml에 추가

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
timeout = 60          # 단위 테스트 기본 타임아웃
markers = [
    "unit: 순수 비즈니스 로직 테스트",
    "integration: 모듈 간 통합 테스트",
    "contract: 스키마/API 계약 테스트",
    "e2e: 엔드투엔드 시나리오 테스트 (느림)",
    "slow: 60초 이상 소요 테스트",
]
addopts = [
    "--strict-markers",
    "-ra",
]

[tool.coverage.run]
source = ["src/ddk"]
omit = ["*/tests/*", "*/__init__.py"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

---

## 5. CI 게이트 매핑

| 이벤트 | 실행 단계 | 블로킹 조건 |
|--------|---------|-----------|
| PR open/push | static + unit + contract | 모두 pass 필수 |
| PR push | integration | pass 필수 (merge 불가) |
| main 머지 | e2e | fail 시 revert |
| tag push | 전체 suite + build + publish | 모두 pass |

---

## 6. 환경 변수 (GitHub Secrets)

| Secret 이름 | 사용 위치 | 필수 여부 |
|------------|---------|---------|
| `ANTHROPIC_API_KEY` | E2E (real LLM 모드) | E2E only |
| `PYPI_TOKEN` | release workflow | release only |

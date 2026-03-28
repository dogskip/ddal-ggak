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

## 스테이징 환경 정의

> `ddk`는 웹 서버가 없는 로컬 CLI 도구이므로 별도의 배포 환경이 필요 없다.
> "스테이징"은 CI에서 실제 fixture 저장소 대상으로 전체 통합 테스트를 실행하는 것을 의미한다.

### CI staging gate 정의

```yaml
# .github/workflows/ci.yml 내 staging job

staging:
  name: Staging Integration
  runs-on: ubuntu-latest
  needs: [integration]          # integration job 통과 후 실행
  environment: staging          # GitHub Environment: staging (branch protection 연동)
  if: github.ref == 'refs/heads/main' || github.event_name == 'pull_request'

  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.12"
    - name: Install uv
      run: curl -LsSf https://astral.sh/uv/install.sh | sh
    - name: Install dependencies
      run: uv sync --all-extras
    - name: Setup fixture repository
      run: |
        git clone https://github.com/ddalggak/fixture-react-vite tests/e2e/fixture-repo
        # 또는 로컬 fixture 생성: python scripts/create_fixture_repo.py
    - name: Run E2E tests (staging)
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY_STAGING }}
        DDK_LOG_FORMAT: json
        DDK_TEST_MODE: "true"       # FakeLLMAdapter 사용 (실제 API 호출 없음)
      run: |
        uv run pytest tests/e2e/ -m "staging" -v --timeout=300
    - name: Upload E2E artifacts
      if: always()
      uses: actions/upload-artifact@v4
      with:
        name: e2e-evidence-${{ github.run_id }}
        path: tests/e2e/output/
```

### 환경 변수 (GitHub Secrets)

| Secret | 용도 | 필수 |
|--------|------|:----:|
| `ANTHROPIC_API_KEY` | 실제 LLM 호출 (E2E only) | E2E에만 필요 |
| `ANTHROPIC_API_KEY_STAGING` | staging LLM 호출 | staging에만 필요 |
| `OPENAI_API_KEY` | fallback provider | 선택 |

> **보안 주의:** API 키는 절대 `.env` 파일로 저장소에 커밋하지 않는다.
> CI에서는 GitHub Secrets만 사용한다.

### 로컬 개발 환경에서의 staging 재현

```bash
# 로컬에서 staging 환경 재현
DDK_TEST_MODE=true uv run pytest tests/e2e/ -m "staging" -v
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

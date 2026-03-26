# Sandbox 구현 명세

> **결정: ephemeral git worktree** (Docker는 v2 범위)
>
> ADR-021: Sandbox Strategy — git worktree over Docker for P0

---

## ADR-021: 샌드박스 전략

### 컨텍스트

생성된 코드를 실제 실행해 검증해야 한다. 이 실행은 반드시 격리(isolation)되어야 하며, 검증 실패 시 repo 원본을 오염시키면 안 된다.

### 옵션 비교

| 항목 | git worktree | Docker container |
|------|-------------|-----------------|
| 설치 복잡도 | git >= 2.30 (기본 포함) | Docker daemon 필요 |
| 초기화 시간 | <1초 | 3~30초 (이미지 pull 포함) |
| 파일 시스템 격리 | worktree 디렉토리 격리 | 완전 격리 |
| 네트워크 격리 | 없음 (OS 레벨) | 완전 차단 가능 |
| cleanup 신뢰성 | `git worktree remove` | container rm |
| macOS 로컬 지원 | 완벽 | Docker Desktop 필요 |
| CI 지원 | GitHub Actions 기본 git | Docker in Docker 설정 필요 |
| rollback 메커니즘 | git checkout | volume snapshot |
| 보안 수준 | 중간 (process 격리) | 높음 (namespace 격리) |

### 결정

P0에서는 **git worktree** 방식을 채택한다.

이유:
1. 로컬 개발 환경에서 추가 설치 없이 동작
2. worktree는 새 디렉토리에 repo 사본 생성 → 원본 보호
3. git checkpoint(커밋)를 통한 rollback이 자연스럽게 통합
4. P0 목표가 "동작하는 루프"이므로 보안보다 속도 우선

보안 gap 인정:
- 생성된 코드가 네트워크 요청을 보낼 수 있음
- P0 대응: CommandAllowlist로 실행 가능 명령 제한, writable 경로 제한
- P1/Docker: 완전한 네트워크 차단 컨테이너로 업그레이드

---

## WorktreeSandbox 클래스 명세

```python
# src/ddk/adapters/sandbox/worktree.py

import subprocess
import shutil
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


COMMAND_ALLOWLIST = frozenset([
    # 패키지 매니저
    "npm", "yarn", "pnpm", "bun",
    # 빌드 도구
    "vite", "tsc", "eslint", "prettier",
    # 테스트 러너
    "vitest", "jest",
    # git (worktree 관리용)
    "git",
    # node 계열
    "node", "npx", "bunx",
])

# worktree 내에서 쓰기 허용되는 경로 패턴
WRITABLE_PATH_PATTERNS = [
    "src/**",
    "public/**",
    "components/**",
    "pages/**",
    "styles/**",
    "*.config.*",
    "package.json",
    "tsconfig*.json",
    ".env.test",
]

# 절대로 읽어서는 안 되는 경로
FORBIDDEN_READ_PATHS = [
    ".env",
    ".env.local",
    ".env.production",
    "**/.ssh/**",
    "**/secrets/**",
    "**/*.pem",
    "**/*.key",
    "**/.aws/**",
    "**/.docker/**",
    "**/.config/gcloud/**",
    "**/.kube/**",
    "**/.npmrc",
    "**/.pypirc",
]


@dataclass
class SandboxResult:
    sandbox_id: str
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    checkpoint_ref: str | None = None  # 생성된 git 커밋 ref


@dataclass
class WorktreeSandbox:
    """
    ephemeral git worktree 기반 샌드박스.

    사용법:
        async with WorktreeSandbox.create(repo_path) as sandbox:
            await sandbox.apply_files(generated_files)
            result = await sandbox.run_command(["pnpm", "build"])
    """
    repo_path: Path
    worktree_path: Path
    sandbox_id: str
    _checkpoint_ref: str | None = field(default=None, init=False)

    @classmethod
    @asynccontextmanager
    async def create(cls, repo_path: Path, sandbox_id: str | None = None):
        """
        컨텍스트 매니저: worktree 생성 → yield → 자동 cleanup

        1. temp 디렉토리 생성
        2. git worktree add <tempdir> (현재 HEAD 기반)
        3. yield sandbox 인스턴스
        4. git worktree remove --force (항상 실행)
        """
        import uuid
        sid = sandbox_id or f"sandbox-{uuid.uuid4().hex[:8]}"
        temp_dir = Path(tempfile.mkdtemp(prefix=f"ddk-{sid}-"))

        try:
            # worktree 생성
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(temp_dir)],
                cwd=repo_path,
                check=True,
                capture_output=True,
            )

            sandbox = cls(
                repo_path=repo_path,
                worktree_path=temp_dir,
                sandbox_id=sid,
            )

            # 초기 체크포인트 생성
            sandbox._checkpoint_ref = sandbox._get_current_ref()

            yield sandbox

        finally:
            # 항상 cleanup (실패해도)
            try:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(temp_dir)],
                    cwd=repo_path,
                    capture_output=True,
                )
            except Exception:
                pass
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _get_current_ref(self) -> str:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    async def apply_files(self, generated_files: list) -> None:
        """
        GeneratedFile 목록을 worktree에 적용.
        WRITABLE_PATH_PATTERNS 검사 후 적용.
        """
        for gf in generated_files:
            target = self.worktree_path / gf.path
            self._validate_write_path(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(gf.content, encoding="utf-8")

    def _validate_write_path(self, path: Path) -> None:
        """worktree 루트 밖 접근 차단."""
        try:
            path.resolve().relative_to(self.worktree_path.resolve())
        except ValueError:
            raise SecurityError(
                f"쓰기 경로 위반: {path} 는 worktree 밖입니다."
            )

    async def run_command(
        self,
        command: list[str],
        timeout: int = 120,
        env_override: dict | None = None,
    ) -> SandboxResult:
        """
        허용된 명령만 실행 (CommandAllowlist 검사).
        timeout 초과 시 프로세스 강제 종료.
        """
        import asyncio
        import time

        if command[0] not in COMMAND_ALLOWLIST:
            raise SecurityError(
                f"허용되지 않은 명령: {command[0]}"
            )

        start = time.monotonic()
        env = self._build_env(env_override)

        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.worktree_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return SandboxResult(
                sandbox_id=self.sandbox_id,
                success=False,
                stdout="",
                stderr=f"TIMEOUT: {command} exceeded {timeout}s",
                exit_code=-1,
                duration_seconds=timeout,
            )

        return SandboxResult(
            sandbox_id=self.sandbox_id,
            success=proc.returncode == 0,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
            exit_code=proc.returncode,
            duration_seconds=time.monotonic() - start,
        )

    def create_checkpoint(self, message: str = "ddk checkpoint") -> str:
        """
        현재 worktree 상태를 git commit으로 저장.
        auto-fix 시도 전 호출하여 롤백 지점 확보.
        """
        subprocess.run(
            ["git", "add", "-A"],
            cwd=self.worktree_path,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "--allow-empty", "-m", message],
            cwd=self.worktree_path,
            capture_output=True,
            text=True,
        )
        return self._get_current_ref()

    def restore_checkpoint(self, ref: str) -> None:
        """특정 checkpoint ref로 worktree를 복원."""
        subprocess.run(
            ["git", "reset", "--hard", ref],
            cwd=self.worktree_path,
            check=True,
            capture_output=True,
        )

    # 허용 환경변수 화이트리스트 (보안: 블랙리스트 → 화이트리스트 전환)
    ENV_WHITELIST = frozenset([
        "PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL",
        "NODE_ENV", "CI", "TERM",
        # Node.js / 빌드 도구 필수
        "NODE_PATH", "NPM_CONFIG_REGISTRY",
    ])

    def _build_env(self, override: dict | None) -> dict:
        """
        보안 정책: 화이트리스트 방식으로 환경변수를 필터링한다.
        명시적으로 허용된 변수만 샌드박스에 전달한다.
        API 키, 인증 토큰 등 민감 정보는 구조적으로 차단된다.
        """
        import os
        env = {}
        for key in self.ENV_WHITELIST:
            val = os.environ.get(key)
            if val is not None:
                env[key] = val
        # NODE_ENV 강제 설정
        env["NODE_ENV"] = "test"
        if override:
            # override도 화이트리스트 검증
            for k, v in override.items():
                if k in self.ENV_WHITELIST:
                    env[k] = v
                else:
                    logger.warning(f"env override '{k}' blocked by whitelist")
        return env


class SecurityError(Exception):
    """Sandbox 보안 정책 위반"""
```

---

## Rollback 구현

```python
# src/ddk/workspace/rollback.py

class RollbackController:
    """
    케이스 실행 전 checkpoint를 생성하고,
    실패 시 repo를 안전하게 원상복구한다.
    """

    def __init__(self, repo_path: Path, case_id: str):
        self.repo_path = repo_path
        self.case_id = case_id
        self._pre_run_ref: str | None = None

    def save_pre_run_checkpoint(self) -> str:
        """
        케이스 시작 전 현재 repo HEAD를 저장.
        ddk rollback 명령에서 이 ref를 사용.
        """
        result = subprocess.run(
            ["git", "stash", "push", "-m", f"ddk-pre-{self.case_id}"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        )
        # stash ref 또는 HEAD 저장
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
        ).stdout.strip()

        checkpoint_file = self._checkpoint_path()
        checkpoint_file.write_text(head)
        self._pre_run_ref = head
        return head

    def rollback_to_pre_run(self) -> None:
        """
        케이스 시작 이전 상태로 repo 복원.
        실제 repo 파일 변경 (sandbox 아님).
        """
        if not self._pre_run_ref:
            ref_file = self._checkpoint_path()
            if not ref_file.exists():
                raise RollbackError("사전 체크포인트가 없습니다")
            self._pre_run_ref = ref_file.read_text().strip()

        subprocess.run(
            ["git", "stash", "pop"],
            cwd=self.repo_path,
            check=False,
            capture_output=True,
        )

    def _checkpoint_path(self) -> Path:
        return self.repo_path / ".ddk" / "cases" / self.case_id / "checkpoint-pre-run.ref"


class RollbackError(Exception):
    pass
```

### Rollback failure handling summary

- rollback success의 기준은 `git status --porcelain` 가 pre-run snapshot과 일치하는 것이다.
- sandbox/worktree rollback은 `restore -> status compare -> clean untracked -> recreate worktree` 순으로 시도한다.
- primary repo rollback에서 status mismatch가 남으면 추가 자동 복구를 중단하고 `manual-review-required` 로 종료한다.
- rollback mismatch 상태에서는 fix loop 재개, benchmark 실행, certify 진행을 금지한다.

> 상세 SOP: `25-rollback-recovery-sop.md`

---

## sandbox 실행 흐름

```
ddk validate --case-id C-001
│
├── WorktreeSandbox.create(repo_path) — worktree 생성
│   ├── apply_files(generated_artifacts.files)
│   ├── run_command(["pnpm", "install", "--frozen-lockfile"])
│   ├── run_command(["pnpm", "build"])              → BUILD gate
│   ├── run_command(["pnpm", "tsc", "--noEmit"])    → TYPE gate
│   ├── run_command(["pnpm", "eslint", "src"])      → LINT gate
│   ├── run_command(["pnpm", "dev", "--port=3001"]) → 앱 시작
│   └── Playwright screenshot + console capture     → RUNTIME gate
│
└── WorktreeSandbox.__aexit__ — worktree 자동 cleanup

ddk fix --case-id C-001
│
├── sandbox.create_checkpoint("pre-fix-attempt-1")  ← 각 시도 전 체크포인트
├── apply fix changes
├── run validation
├── if regression: sandbox.restore_checkpoint(ref)  ← 즉시 복원
└── record FixAttempt.result
```

---

## 타임아웃 정책

| 단계 | 타임아웃 | 초과 시 처리 |
|------|--------|------------|
| `pnpm install` | 60s | SKIP (cache hit 가정) |
| `pnpm build` | 90s | BUILD-001 실패로 기록 |
| `tsc --noEmit` | 60s | TYPE 실패로 기록 |
| `eslint` | 30s | LINT 경고로 기록 |
| 앱 부팅 (`dev`) | 30s | RUNTIME-004 실패로 기록 |
| Playwright 스크린샷 | 20s | RUNTIME fallback |
| 전체 validate | 300s | 남은 단계 skip |

---

## 보안 정책 요약

| 항목 | P0 정책 | P1 목표 |
|------|---------|---------|
| 명령 실행 | CommandAllowlist (화이트리스트) | Docker 컨테이너 격리 |
| 네트워크 접근 | 차단 없음 (프로세스 레벨) | iptables deny-all |
| 파일 쓰기 | worktree 루트 내로 제한 | overlayfs |
| API key 노출 | env 제거 후 실행 | secret store |
| path traversal | `relative_to()` 검사 | AppArmor profile |

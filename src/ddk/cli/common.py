"""State and helpers shared by every command."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from rich.console import Console

from ddk.i18n import t
from ddk.models.config import DdalggakConfig, observe_settings
from ddk.workspace.manager import WorkspaceManager

from .contract import CommandFailureError, capture

console = Console()
err_console = Console(stderr=True, style="red")
status_console = Console(stderr=True)

_SECRET_NAME_PARTS = ("KEY", "SECRET", "TOKEN", "PASSWORD")


class State:
    """Global options and the settings read once at start-up."""

    flag_overrides: dict[str, Any] = {}
    config: DdalggakConfig | None = None
    config_error: ValueError | OSError | None = None


state = State()


def is_interactive() -> bool:
    """Whether someone can answer a question: input and output are both a terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def load_settings(repo: Path | None = None, overrides: dict[str, Any] | None = None) -> None:
    """Read the settings from the environment; a malformed one is kept for ``get_config``."""
    state.config_error = None
    try:
        state.config = observe_settings(
            repo or Path.cwd(), {**state.flag_overrides, **(overrides or {})}
        )[0]
    except (ValueError, OSError) as exc:
        state.config = None
        state.config_error = exc


def get_config(repo: Path | None = None, overrides: dict[str, Any] | None = None) -> DdalggakConfig:
    """The settings, or a message naming each malformed variable and exit code 3."""
    if repo is not None or overrides is not None:
        load_settings(repo, overrides)
    if state.config_error is not None:
        err_console.print(t("❌ 설정 오류 — 환경 변수나 .env 값을 확인하세요:"))
        errors = (
            state.config_error.errors() if isinstance(state.config_error, ValidationError) else []
        )
        for problem in errors:
            name = _variable_name(problem["loc"])
            shown = ""
            if not is_secret_setting(name):
                shown = t(" (입력값: {value})", value=repr(problem.get("input")))
            err_console.print(f"   {name}: {problem['msg']}{shown}", markup=False, highlight=False)
        raise CommandFailureError("configuration", "invalid_settings")
    return state.config or DdalggakConfig()


def _variable_name(loc: tuple[int | str, ...]) -> str:
    field = str(loc[0]) if loc else "?"
    # Aliased settings (API keys) already carry their full environment name.
    return field if field.isupper() else f"DDK_{field.upper()}"


def is_secret_setting(name: str) -> bool:
    return any(part in name.upper() for part in _SECRET_NAME_PARTS)


def require_api_key(cfg: DdalggakConfig) -> None:
    if not cfg.anthropic_api_key:
        err_console.print(t("❌ ANTHROPIC API 키가 없습니다."))
        err_console.print(t("   설정 방법: export DDK_ANTHROPIC_API_KEY=sk-ant-..."))
        err_console.print(t("            또는 export ANTHROPIC_API_KEY=sk-ant-..."))
        err_console.print(t("   또는 .env 파일에 DDK_ANTHROPIC_API_KEY=... 추가"))
        raise CommandFailureError("configuration", "api_key_required")


def resolve_case_path(repo: Path, case_id: str | None) -> Path:
    """Resolve a case directory, defaulting to the latest case when omitted."""
    manager = WorkspaceManager(repo.resolve())
    resolved_case_id = case_id or manager.latest_case_id()
    if resolved_case_id is None:
        err_console.print(t("❌ 조회할 case가 없습니다. 먼저 `ddk run`을 실행하세요."))
        raise CommandFailureError("blocked", "case_not_found")
    case_path = manager.case_dir(resolved_case_id)
    if not case_path.exists():
        err_console.print(t("❌ case 폴더를 찾을 수 없습니다: {path}", path=case_path))
        raise CommandFailureError("blocked", "case_not_found")
    return case_path


def print_json(payload: dict[str, Any]) -> None:
    """Render structured CLI output as JSON.

    ``markup=False`` + ``soft_wrap=True`` keep Rich from interpreting ``[..]`` as
    markup or hard-wrapping long lines, both of which corrupt machine-parsable
    JSON for large payloads.
    """
    if capture(payload):
        return
    console.print(
        json.dumps(payload, ensure_ascii=False, indent=2),
        markup=False,
        soft_wrap=True,
    )

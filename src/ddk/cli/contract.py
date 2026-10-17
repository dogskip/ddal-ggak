"""One public response envelope and an explicit process-exit registry."""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys
from collections.abc import Sequence
from contextlib import nullcontext, redirect_stdout
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from typer.core import TyperGroup

from ddk.i18n import t
from ddk.models.verified_change import Record

SCHEMA_VERSION = "ddk/2"
EXIT_CODES = {
    "success": 0,
    "blocked": 1,
    "usage": 2,
    "configuration": 3,
    "unavailable": 4,
    "integrity": 5,
    "interrupted": 130,
}


def exit_descriptions() -> dict[str, str]:
    return {
        "success": t("작업 완료 또는 검증 통과"),
        "blocked": t("인수 기준 미달 또는 사례 없음"),
        "usage": t("명령 사용법 오류"),
        "configuration": t("입력·설정 무효 또는 승인 없음"),
        "unavailable": t("실행 환경 사용 불가"),
        "integrity": t("증거 재검사 또는 현재 소스 일치 실패"),
        "interrupted": t("사용자 실행 중단"),
    }


class CommandFailureError(Exception):
    def __init__(self, category: str, code: str, message: str = "") -> None:
        self.category = category
        self.code = code
        self.message = message or code
        super().__init__(self.message)


@dataclass
class Session:
    command: str
    as_json: bool
    payload: Record | None = None
    arguments: tuple[str, ...] = ()


_SESSION: ContextVar[Session | None] = ContextVar("ddk_cli_response", default=None)


def command_name() -> str:
    session = _SESSION.get()
    return session.command if session else "ddk"


def warn_deprecated(old: str, new: str) -> None:
    session = _SESSION.get()
    if old.startswith("--") and (
        session is None
        or not any(arg == old or arg.startswith(old + "=") for arg in session.arguments)
    ):
        return
    sys.stderr.write(t("호환 이름 {old} 대신 {new}를 사용하세요.", old=old, new=new) + "\n")


def capture(payload: Record) -> bool:
    session = _SESSION.get()
    if session is None or not session.as_json:
        return False
    if session.payload is not None:
        raise CommandFailureError("integrity", "duplicate_result")
    session.payload = payload
    return True


def envelope(
    command: str,
    data: Record,
    *,
    status: str = "ok",
    code: str | None = None,
    message: str = "",
    actions: Sequence[object] | None = None,
) -> Record:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "data": data,
        "error": {"code": code, "message": message or code} if code else None,
        "actions": list(actions) if actions is not None else list(data.get("actions", [])),
    }


ACTION_EXIT_CODES = {
    "isolation_unavailable": EXIT_CODES["unavailable"],
    "environment_gap": EXIT_CODES["unavailable"],
    "ambiguous_baseline": EXIT_CODES["configuration"],
    "baseline_mismatch": EXIT_CODES["configuration"],
    "ambiguous_change_requirements": EXIT_CODES["configuration"],
    "invalid_change_requirements": EXIT_CODES["configuration"],
}


def operation_exit(command: str, record: Record) -> int:
    if command in {"change gate", "ddk_gate_status"}:
        return 0 if record.get("gate_status") == "passed" else EXIT_CODES["integrity"]
    if command in {"change replay", "ddk_replay"}:
        return 0 if record.get("evidence_integrity") is True else EXIT_CODES["integrity"]
    if record.get("status") == "cancelled":
        return EXIT_CODES["interrupted"]
    if record.get("status") == "blocked":
        codes = {
            ACTION_EXIT_CODES.get(action.get("code"), 1) for action in record.get("actions", [])
        }
        return 4 if 4 in codes else 3 if 3 in codes else 1
    if (
        command
        in {
            "up",
            "change verify",
            "change repair",
            "change status",
            "ddk_verify",
            "ddk_status",
            "ddk_repair",
        }
        and "decision" in record
    ):
        if record["decision"] == "blocked":
            codes = {
                ACTION_EXIT_CODES.get(action.get("code"), 1) for action in record.get("actions", [])
            }
            return 4 if 4 in codes else 3 if 3 in codes else 1
        return {"ready": 0, "manual-review": 1}.get(record["decision"], 3)
    if command in {"change apply", "change recover", "ddk_apply"} and "state" in record:
        return {"applied": 0, "rolled_back": 0, "conflict": 1, "unknown": 1}.get(record["state"], 3)
    return EXIT_CODES["success"]


def safe_code(error: BaseException) -> str:
    candidate = str(error).partition(":")[0]
    if re.fullmatch(r"[a-z][a-z0-9_]{0,79}", candidate):
        return candidate
    return "file_unavailable" if isinstance(error, OSError) else "invalid_request"


def exception_failure(command: str, error: BaseException) -> CommandFailureError:
    if isinstance(error, CommandFailureError):
        return error
    if (
        isinstance(error, KeyboardInterrupt | asyncio.CancelledError)
        or type(error).__name__ == "Abort"
    ):
        return CommandFailureError("interrupted", "cancelled")
    if getattr(error, "exit_code", None) == 2:
        return CommandFailureError("usage", "usage_error", str(error))
    category = (
        "integrity"
        if command in {"change replay", "change gate", "ddk_replay", "ddk_gate_status"}
        else "configuration"
    )
    if isinstance(error, PermissionError | RuntimeError):
        category = "unavailable"
    return CommandFailureError(category, safe_code(error))


def response(command: str, data: Record, exit_code: int) -> Record:
    if data.get("schema_version") == SCHEMA_VERSION:
        result = dict(data)
        result["command"] = command
        if exit_code >= 2:
            result["status"] = "error"
        return result
    status = (
        "cancelled"
        if exit_code == 130
        else "blocked"
        if exit_code == 1
        else "error"
        if exit_code
        else "ok"
    )
    return envelope(command, data, status=status)


class ContractGroup(TyperGroup):
    def _command_label(self, args: Sequence[str]) -> str:
        selected: list[str] = []
        command: Any = self
        index = 0
        while index < len(args) and getattr(command, "commands", None):
            token = args[index]
            if token in command.commands:
                selected.append(token)
                command = command.commands[token]
                index += 1
                continue
            parameter = next((p for p in command.params if token in getattr(p, "opts", [])), None)
            index += 2 if parameter is not None and not getattr(parameter, "is_flag", False) else 1
        return " ".join(selected) or "ddk"

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        arguments = list(sys.argv[1:] if args is None else args)
        session = Session(
            self._command_label(arguments), "--json" in arguments, arguments=tuple(arguments)
        )
        token = _SESSION.set(session)
        output = io.StringIO()
        failure: CommandFailureError | None = None
        exit_code = 0
        try:
            with redirect_stdout(output) if session.as_json else nullcontext():
                result = super().main(
                    args=arguments,
                    prog_name=prog_name,
                    complete_var=complete_var,
                    standalone_mode=False,
                    windows_expand_args=windows_expand_args,
                    **extra,
                )
                exit_code = result if isinstance(result, int) else 0
        except (Exception, KeyboardInterrupt, asyncio.CancelledError) as error:
            failure = exception_failure(session.command, error)
            exit_code = EXIT_CODES[failure.category]
        finally:
            _SESSION.reset(token)
        if session.as_json:
            if failure:
                payload = envelope(
                    session.command,
                    session.payload or {},
                    status="cancelled"
                    if exit_code == 130
                    else "blocked"
                    if exit_code == 1
                    else "error",
                    code=failure.code,
                    message=failure.message,
                )
            else:
                payload = response(session.command, session.payload or {}, exit_code)
                if (
                    exit_code
                    and payload.get("error") is None
                    and (exit_code >= 2 or not session.payload)
                ):
                    category = next(
                        (name for name, number in EXIT_CODES.items() if number == exit_code),
                        "unavailable",
                    )
                    payload["error"] = {"code": category, "message": category}
            if output.getvalue().strip():
                sys.stderr.write(output.getvalue())
            sys.stdout.write(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")
        elif failure:
            sys.stderr.write(f"Error: {failure.message}\n")
        if standalone_mode:
            raise SystemExit(exit_code)
        return exit_code

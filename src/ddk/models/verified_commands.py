"""Bounded argument arrays shared by configuration compilation and execution."""

from __future__ import annotations

from typing import cast


def command_arguments(value: object, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("invalid_command_argv")
    parts = cast(list[object], value)
    if (
        (not allow_empty and not parts)
        or len(parts) > 100
        or not all(
            isinstance(arg, str) and 0 < len(arg) <= 2048 and "\x00" not in arg for arg in parts
        )
    ):
        raise ValueError("invalid_command_argv")
    return cast(list[str], parts)

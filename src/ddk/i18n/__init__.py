"""Message language: Korean source text, with an English entry for each message."""

from __future__ import annotations

import os
from typing import Literal

from .english import ENGLISH

Language = Literal["ko", "en"]

# Checked in this order; the first one that is set decides.
_LANGUAGE_VARIABLES = ("DDK_LANG", "LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE")

__all__ = ["ENGLISH", "Language", "language", "t"]


def language() -> Language:
    """``ko`` when the first language variable that is set starts with ``ko``, else ``en``."""
    for name in _LANGUAGE_VARIABLES:
        value = os.environ.get(name, "").strip().lower()
        if value:
            return "ko" if value.startswith("ko") else "en"
    return "en"


def t(message: str, /, **values: object) -> str:
    """``message`` in the active language, with each ``{name}`` filled from ``values``.

    The argument must be a string literal: the catalog test finds messages by reading the source.
    """
    text = ENGLISH.get(message, message) if language() == "en" else message
    return text.format(**values) if values else text

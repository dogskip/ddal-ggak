"""The ``ddk`` command line."""

from __future__ import annotations

# Each module registers its commands on the shared application when it is imported.
from . import delivery, demo, evidence, studio, workspace  # noqa: F401
from .app import app, cli_main, main

__all__ = ["app", "cli_main", "main"]

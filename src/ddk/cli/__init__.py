"""The ``ddk`` command line."""

from __future__ import annotations

# Each module registers its commands on the shared application when it is imported.
from . import delivery as delivery
from . import demo as demo
from . import evidence as evidence
from . import studio as studio
from . import verified as verified
from . import workspace as workspace
from .app import app, cli_main, main

__all__ = ["app", "cli_main", "main"]

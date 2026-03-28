"""Structured logging configuration with secret redaction — INFRA-05.

Usage::

    from ddk.logging.setup import configure_logging
    configure_logging(level="INFO", log_format="json", redact=True)
"""

from __future__ import annotations

import logging
from typing import Any

import structlog

from ddk.security.redact import redact_dict


class RedactingProcessor:
    """structlog processor that scrubs secrets from every log event dict.

    Registered as the last processor before rendering so redaction applies
    to the fully-assembled event_dict (including keys added by earlier processors).
    """

    def __call__(
        self,
        logger: Any,
        method: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply redact_dict to the entire structlog event_dict.

        Args:
            logger: The bound logger (unused, required by structlog protocol).
            method: Log level string (unused).
            event_dict: Structlog event dict to redact.

        Returns:
            New event_dict with all string values redacted.
        """
        return redact_dict(event_dict)


def configure_logging(
    level: str = "INFO",
    log_format: str = "json",
    *,
    redact: bool = True,
) -> None:
    """Configure structlog for the ddk CLI and MCP server.

    Args:
        level: Python logging level string (DEBUG, INFO, WARNING, ERROR).
        log_format: ``"json"`` for structured JSON output (default, suitable for
            log aggregation), or ``"console"`` for human-readable dev output.
        redact: When *True* (default), secret patterns are replaced with
            ``[REDACTED]`` before rendering.
    """
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if redact:
        shared_processors.append(RedactingProcessor())

    if log_format == "json":
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Wire stdlib formatter for root handler
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    root_handler = logging.root.handlers[0] if logging.root.handlers else logging.StreamHandler()
    root_handler.setFormatter(formatter)
    if not logging.root.handlers:
        logging.root.addHandler(root_handler)

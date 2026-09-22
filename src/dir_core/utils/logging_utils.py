"""
Logging helpers: DFID on every decision-path line.

Preferred: ``configure_console_logging()`` plus ``with log_context(dfid=...):``.
A logging Filter copies the ContextVar onto each record; the formatter renders it.
``log_with_dfid`` remains for samples that still pass DFID at the call site.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Optional

DEFAULT_DFID = "-"
CONSOLE_FORMAT = "%(levelname)s [DFID=%(dfid)s] %(message)s"

dfid_context: ContextVar[str] = ContextVar("dfid", default=DEFAULT_DFID)


class DfidContextFilter(logging.Filter):
    """Attach the current DFID to every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.dfid = dfid_context.get()
        return True


@contextmanager
def log_context(*, dfid: str) -> Generator[None, None, None]:
    """Bind DFID for the current flow; nested logs pick it up automatically."""
    token = dfid_context.set(str(dfid) if dfid else DEFAULT_DFID)
    try:
        yield
    finally:
        dfid_context.reset(token)


def configure_console_logging(level: int | str | None = None) -> None:
    """Root StreamHandler with DFID filter. Level from LOG_LEVEL when omitted."""
    if level is None:
        level_name = os.environ.get("LOG_LEVEL", "INFO")
        resolved = getattr(logging, str(level_name).upper(), logging.INFO)
    elif isinstance(level, str):
        resolved = getattr(logging, level.upper(), logging.INFO)
    else:
        resolved = level

    handler = logging.StreamHandler()
    handler.addFilter(DfidContextFilter())
    handler.setFormatter(logging.Formatter(CONSOLE_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)


def log_with_dfid(
    logger: logging.Logger,
    dfid: Optional[str],
    level: int,
    msg: str,
    *args: Any,
    **kwargs: Any,
) -> None:
    """Log message with [DFID=...] prefix when dfid is set."""
    if dfid:
        msg = f"[DFID={dfid}] {msg}"
    logger.log(level, msg, *args, **kwargs)


def format_dfid_prefix(dfid: Optional[str]) -> str:
    """Return '[DFID=...] ' or '' for use in custom format."""
    return f"[DFID={dfid}] " if dfid else ""

"""
Logging helpers: DFID in every log line for traceability.

Use log_with_dfid(logger, dfid, level, msg, *args, **kwargs) or bind dfid to context.
"""

import logging
from typing import Any, Optional


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

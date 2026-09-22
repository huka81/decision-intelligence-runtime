"""
Supporting utilities for DIR/ROA samples.

Components used in examples but not part of core DIR specification:
- Logging helpers: log_context, configure_console_logging, log_with_dfid
- LLM: OllamaClient (local), GeminiClient (cloud)

For SQLite file bootstrap before wiring backends, use ``dir_core.storage.ensure_db``.
"""

from .llm_client import LLMClient
from .logging_utils import (
    DfidContextFilter,
    configure_console_logging,
    format_dfid_prefix,
    log_context,
    log_with_dfid,
)

__all__ = [
    "DfidContextFilter",
    "configure_console_logging",
    "format_dfid_prefix",
    "log_context",
    "log_with_dfid",
    "LLMClient",
]

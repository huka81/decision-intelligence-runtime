"""
Supporting utilities for DIR/ROA samples.

Components used in examples but not part of core DIR specification:
- Logging helpers: log_with_dfid, format_dfid_prefix
- LLM: OllamaClient (local), GeminiClient (cloud)

For SQLite file bootstrap before wiring backends, use ``dir_core.storage.ensure_db``.
"""

from .llm_client import LLMClient
from .logging_utils import format_dfid_prefix, log_with_dfid

__all__ = [
    "log_with_dfid",
    "format_dfid_prefix",
    "LLMClient",
]

"""
Supporting utilities for DIR/ROA samples.

Components used in examples but not part of core DIR specification:
- Logging helpers: log_with_dfid, format_dfid_prefix
- Config: load_yaml_config (unified YAML loading for all samples)
- LLM: OllamaClient (local), GeminiClient (cloud)

For SQLite file bootstrap before wiring backends, use ``dir_core.storage.ensure_db``.
"""

from .config_loader import load_yaml_config
from .llm_client import LLMClient
from .logging_utils import format_dfid_prefix, log_with_dfid

__all__ = [
    "load_yaml_config",
    "log_with_dfid",
    "format_dfid_prefix",
    "LLMClient",
]

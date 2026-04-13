"""
Supporting utilities for DIR/ROA samples.

Components used in examples but not part of core DIR specification:
- Market simulation: QuoteGenerator, NewsGenerator, QuoteTick, NewsEvent
- Logging helpers: log_with_dfid, format_dfid_prefix
- Config: load_yaml_config (unified YAML loading for all samples)
- LLM: OllamaClient (local), GeminiClient (cloud)

For SQLite file bootstrap before wiring backends, use ``dir_core.storage.ensure_db``.
"""

from .config_loader import load_yaml_config
from .llm_client import GeminiClient, LLMClient, OllamaClient, check_ollama
from .logging_utils import format_dfid_prefix, log_with_dfid
from .market_events import NewsEvent, QuoteTick
from .news_generator import NEWS_HEADLINE_TEMPLATES, NewsGenerator, score_news
from .quote_generator import QuoteGenerator

__all__ = [
    "load_yaml_config",
    "QuoteTick",
    "NewsEvent",
    "QuoteGenerator",
    "NewsGenerator",
    "score_news",
    "NEWS_HEADLINE_TEMPLATES",
    "log_with_dfid",
    "format_dfid_prefix",
    "LLMClient",
    "OllamaClient",
    "GeminiClient",
    "check_ollama",
]

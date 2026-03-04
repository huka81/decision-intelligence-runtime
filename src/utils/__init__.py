"""
Supporting utilities for DIR/ROA samples.

Components used in examples but not part of core DIR specification:
- Market simulation: QuoteGenerator, NewsGenerator, QuoteTick, NewsEvent
- Logging helpers: log_with_dfid, format_dfid_prefix
- Config: load_yaml_config (unified YAML loading for all samples)
- Bootstrap: ensure_db (SQLite DB and tables setup)
- LLM: OllamaClient (local), GeminiClient (cloud)
"""

from .bootstrap_sqlite import ensure_db
from .config_loader import load_yaml_config
from .gemini_client import GeminiClient
from .logging_utils import format_dfid_prefix, log_with_dfid
from .market_events import NewsEvent, QuoteTick
from .news_generator import NEWS_HEADLINE_TEMPLATES, NewsGenerator, score_news
from .ollama_client import LLMClient, OllamaClient, check_ollama
from .quote_generator import QuoteGenerator

__all__ = [
    "ensure_db",
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

"""
``31_finance_trading`` test doubles and synthetic streams.

* ``llm_mock_strategy`` — deterministic ``MockLLMClient`` responses for ROA.
* ``QuoteGenerator`` / ``NewsGenerator`` — price ticks and news payloads for EOAM.

Kernel code lives under ``src/dir_core``; orchestration in ``run.py`` / ``orchestrator.py``;
canonical persistence via ``telemetry`` and ``StorageBundle`` from ``shared.bootstrap``.
"""

from .llm_mock_strategy import make_mock_strategy
from .market_events import NewsEvent, QuoteTick
from .news_generator import NEWS_HEADLINE_TEMPLATES, NewsGenerator, score_news
from .quote_generator import QuoteGenerator

__all__ = [
    "NEWS_HEADLINE_TEMPLATES",
    "NewsEvent",
    "NewsGenerator",
    "QuoteGenerator",
    "QuoteTick",
    "make_mock_strategy",
    "score_news",
]

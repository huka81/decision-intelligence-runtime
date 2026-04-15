"""
Synthetic market context for the finance trading sample.

Quote ticks, news, and event-bus payloads for EOAM demos.
"""

from .market_events import NewsEvent, QuoteTick
from .news_generator import NEWS_HEADLINE_TEMPLATES, NewsGenerator, score_news
from .quote_generator import QuoteGenerator

__all__ = [
    "NewsEvent",
    "NEWS_HEADLINE_TEMPLATES",
    "NewsGenerator",
    "QuoteGenerator",
    "QuoteTick",
    "score_news",
]

"""
Test doubles for ``09_topology_a_eoam``.

``QuoteGenerator`` / ``QuoteTick`` match ``samples/31_finance_trading/mocks`` for the same
EOAM observation payload shape.
"""

from .market_events import NewsEvent, QuoteTick
from .quote_generator import QuoteGenerator

__all__ = ["NewsEvent", "QuoteGenerator", "QuoteTick"]

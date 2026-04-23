"""
Market simulation event models: QuoteTick, NewsEvent.

Part of mocks: payloads align with OBSERVATION/MARKET_SIGNAL and NEWS on the event bus.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# =============================================================================
# Quote stream (market ticks)
# =============================================================================


class QuoteTick(BaseModel):
    """Single quote/tick for market simulation.

    Aligns with MARKET_SIGNAL / OBSERVATION payload in samples (instrument, price,
    price_delta_pct, volatility, trend, volume, timestamp).
    """

    instrument: str = Field(description="Instrument symbol, e.g. BTC-USD")
    timestamp: datetime = Field(default_factory=_utcnow)
    mid_price: float = Field(description="Mid price")
    bid: Optional[float] = Field(default=None, description="Bid price")
    ask: Optional[float] = Field(default=None, description="Ask price")
    volume: float = Field(default=0.0, description="Volume")
    price_delta_pct: Optional[float] = Field(default=None, description="Percent change from previous tick")
    volatility: Optional[float] = Field(default=None, description="Volatility (e.g. rolling or constant)")
    trend: Optional[str] = Field(default=None, description="bullish / bearish / neutral")

    def to_payload(self) -> Dict[str, Any]:
        """Convert to dict payload for EventBus (MARKET_SIGNAL / OBSERVATION)."""
        return {
            "instrument": self.instrument,
            "price": self.mid_price,
            "price_delta_pct": self.price_delta_pct if self.price_delta_pct is not None else 0.0,
            "volatility": self.volatility if self.volatility is not None else 0.0,
            "volume": self.volume,
            "timestamp": self.timestamp.isoformat(),
            "trend": self.trend or "neutral",
        }


# =============================================================================
# News events
# =============================================================================


class NewsEvent(BaseModel):
    """Market news event for simulation.

    Used as NEWS event payload. sentiment in [-1, 1] or [0, 1] depending on convention.
    """

    news_id: str = Field(description="Unique identifier for this news item")
    timestamp: datetime = Field(default_factory=_utcnow)
    headline: str = Field(description="Headline text")
    sentiment: float = Field(ge=-1.0, le=1.0, description="Sentiment score, -1 bearish to 1 bullish")
    category: str = Field(default="general", description="e.g. macro, earnings, regulatory")
    instruments_affected: List[str] = Field(default_factory=list, description="Instrument symbols affected")
    raw_score: Optional[float] = Field(default=None, description="Raw relevance/quality score from generator")
    source: str = Field(default="simulator", description="Origin of the news")

    def to_payload(self, dfid: Optional[str] = None) -> Dict[str, Any]:
        """Convert to dict payload for EventBus (NEWS)."""
        payload: Dict[str, Any] = {
            "news_id": self.news_id,
            "timestamp": self.timestamp.isoformat(),
            "headline": self.headline,
            "sentiment": self.sentiment,
            "category": self.category,
            "instruments_affected": self.instruments_affected,
            "raw_score": self.raw_score,
            "source": self.source,
        }
        if dfid is not None:
            payload["dfid"] = dfid
        return payload

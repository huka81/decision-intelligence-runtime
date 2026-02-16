"""
News event generator for market simulation.

Produces NewsEvents with headline templates, sentiment, category, and
a simple scoring function (relevance + sentiment strength). Yields events
at configurable intervals for EOAM demo.
"""

import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from .market_events import NewsEvent


# Default headline templates; {instrument} and {pct} can be filled.
NEWS_HEADLINE_TEMPLATES = [
    "Fed signals rate hold; markets steady",
    "{instrument} volatility spikes on macro data",
    "Earnings beat for {instrument} sector",
    "Regulatory update affects {instrument} trading",
    "Institutional flow into {instrument}",
    "Technical breakout on {instrument}",
    "Risk-off sentiment weighs on {instrument}",
    "Strong demand for {instrument} in Asia session",
    "Supply shock reported for {instrument}",
    "Analysts upgrade {instrument} outlook",
]

CATEGORY_WEIGHTS: Dict[str, float] = {
    "macro": 0.9,
    "earnings": 0.85,
    "regulatory": 0.8,
    "technical": 0.6,
    "general": 0.5,
}


def score_news(
    headline: str,
    sentiment: float,
    category: str,
    instruments_affected: List[str],
    noise_scale: float = 0.05,
    rng: Optional[random.Random] = None,
) -> float:
    """Compute a simple quality/relevance score in [0, 1].

    Formula: base + sentiment strength + category weight + small noise.
    Pass rng for deterministic scoring when seed is set.
    """
    base = 0.5
    sentiment_strength = 0.3 * abs(sentiment)
    cat_weight = CATEGORY_WEIGHTS.get(category, 0.5) * 0.2
    rand = rng.random() if rng else random.random()
    noise = (rand - 0.5) * 2 * noise_scale
    raw = base + sentiment_strength + cat_weight + noise
    return max(0.0, min(1.0, raw))


class NewsGenerator:
    """Generator of market news events with scoring.

    Parameters:
        instruments: List of instrument symbols to use in headlines.
        seed: Optional RNG seed for reproducibility.
        interval_sec: Approximate seconds between news events (or use random interval).
        random_interval: If True, use exponential distribution around interval_sec.
    """

    def __init__(
        self,
        instruments: List[str],
        seed: Optional[int] = None,
        interval_sec: float = 10.0,
        random_interval: bool = True,
    ):
        self.instruments = instruments or ["BTC-USD", "ETH-USD"]
        self._rng = random.Random(seed)
        self.interval_sec = interval_sec
        self.random_interval = random_interval
        self._count = 0

    def _next_interval(self) -> float:
        if not self.random_interval:
            return self.interval_sec
        # Exponential: mean = interval_sec
        return self._rng.expovariate(1.0 / self.interval_sec)

    def next_news(self) -> NewsEvent:
        """Produce one news event (no sleep)."""
        self._count += 1
        template = self._rng.choice(NEWS_HEADLINE_TEMPLATES)
        n_instruments = min(2, max(1, self._rng.randint(1, len(self.instruments))))
        affected = self._rng.sample(self.instruments, n_instruments)
        instrument = affected[0]
        headline = template.format(instrument=instrument, pct=f"{self._rng.uniform(-5, 5):.1f}%")
        sentiment = self._rng.uniform(-1.0, 1.0)
        category = self._rng.choice(list(CATEGORY_WEIGHTS.keys()))
        raw_score = score_news(headline, sentiment, category, affected, rng=self._rng)
        return NewsEvent(
            news_id=f"news-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc),
            headline=headline,
            sentiment=round(sentiment, 4),
            category=category,
            instruments_affected=affected,
            raw_score=round(raw_score, 4),
            source="simulator",
        )

    def news_events(self, max_events: Optional[int] = None, sleep_between: bool = True) -> Iterator[NewsEvent]:
        """Yield NewsEvents. If sleep_between, sleeps between events."""
        count = 0
        while True:
            yield self.next_news()
            count += 1
            if max_events is not None and count >= max_events:
                break
            if sleep_between:
                time.sleep(self._next_interval())

    def news_payloads(
        self,
        max_events: Optional[int] = None,
        sleep_between: bool = True,
        dfid: Optional[str] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield news event payloads (dict) for EventBus NEWS type."""
        for event in self.news_events(max_events=max_events, sleep_between=sleep_between):
            yield event.to_payload(dfid=dfid)

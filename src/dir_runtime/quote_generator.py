"""
Quote stream generator for market simulation.

Produces a sequence of ticks (price, volume, trend) compatible with
MARKET_SIGNAL / OBSERVATION payloads. Uses a simple multiplicative random walk
in price for deterministic, reproducible simulation when seed is set.
"""

import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, Optional

from .market_events import QuoteTick


class QuoteGenerator:
    """Generator of quote ticks for one instrument.

    Parameters:
        instrument: Symbol, e.g. "BTC-USD".
        initial_price: Starting mid price.
        volatility: Scale of random moves (e.g. 0.02 for ~2% moves).
        seed: Optional RNG seed for reproducibility.
        tick_interval_sec: Seconds between ticks when using time-based iteration.
        emit_on_change_threshold: If set, emit only when |price_delta_pct| > this (fraction).
    """

    def __init__(
        self,
        instrument: str,
        initial_price: float = 100.0,
        volatility: float = 0.02,
        seed: Optional[int] = None,
        tick_interval_sec: float = 1.0,
        emit_on_change_threshold: Optional[float] = None,
    ):
        self.instrument = instrument
        self.initial_price = initial_price
        self.volatility = volatility
        self.tick_interval_sec = tick_interval_sec
        self.emit_on_change_threshold = emit_on_change_threshold
        self._rng = random.Random(seed)
        self._price = initial_price
        self._prev_price = initial_price
        self._tick_count = 0

    def _next_price(self) -> float:
        """One step of multiplicative random walk: price *= (1 + volatility * Z)."""
        z = self._rng.gauss(0.0, 1.0)
        self._prev_price = self._price
        self._price *= 1.0 + self.volatility * z
        return self._price

    def _trend_from_delta(self, delta_pct: float) -> str:
        if delta_pct > 0.001:
            return "bullish"
        if delta_pct < -0.001:
            return "bearish"
        return "neutral"

    def _volume_noise(self) -> float:
        """Random volume for realism (non-negative)."""
        return max(0.0, self._rng.gauss(1000.0, 500.0))

    def next_tick(self) -> QuoteTick:
        """Produce the next tick (no sleep)."""
        self._next_price()
        self._tick_count += 1
        delta_pct = (self._price - self._prev_price) / self._prev_price if self._prev_price else 0.0
        trend = self._trend_from_delta(delta_pct)
        return QuoteTick(
            instrument=self.instrument,
            timestamp=datetime.now(timezone.utc),
            mid_price=round(self._price, 2),
            volume=self._volume_noise(),
            price_delta_pct=round(delta_pct, 6),
            volatility=self.volatility,
            trend=trend,
        )

    def ticks(self, max_ticks: Optional[int] = None, sleep_between: bool = True) -> Iterator[Dict[str, Any]]:
        """Yield tick payloads (dict) for EventBus.

        If sleep_between is True, sleeps tick_interval_sec between ticks.
        If max_ticks is set, stops after that many ticks.
        """
        count = 0
        while True:
            tick = self.next_tick()
            payload = tick.to_payload()
            if self.emit_on_change_threshold is not None:
                if abs(payload["price_delta_pct"]) < self.emit_on_change_threshold:
                    continue
            yield payload
            count += 1
            if max_ticks is not None and count >= max_ticks:
                break
            if sleep_between and self.tick_interval_sec > 0:
                time.sleep(self.tick_interval_sec)

    def ticks_no_sleep(self, n: int) -> Iterator[Dict[str, Any]]:
        """Yield n tick payloads without sleeping (e.g. for batch or fast demo)."""
        for _ in range(n):
            yield self.next_tick().to_payload()

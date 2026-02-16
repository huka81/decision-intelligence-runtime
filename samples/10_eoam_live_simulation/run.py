#!/usr/bin/env python3
"""
10_eoam_live_simulation - Topology A (EOAM) with live-like quote and news simulation.

Demonstrates:
- QuoteGenerator: stream of market ticks (price, volatility, trend)
- NewsGenerator: market news events with scoring
- Reactive agents: Instrument (OPEN_POSITION, HOLD), NewsScoring (NEWS_QUALIFIED), Position (CLOSE, TAKE_PROFIT, HOLD)
- Priority-based arbitration (RISK_ALERT > CLOSE > OPEN_POSITION > NEWS_QUALIFIED > HOLD)
- DIM validation; mock execution
- Dynamic creation of PositionAgents when OPEN_POSITION wins

Run from repo root: python samples/10_eoam_live_simulation/run.py
Requires: pip install -e . (PYTHONPATH to src/)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dir_runtime import (
    EventBus,
    EventMetadata,
    EventType,
    PolicyProposal,
    create_event_bus,
    new_dfid,
)
from dir_runtime.dim import validate_proposal

def validate(proposal: PolicyProposal) -> tuple[str, str]:
    """Shim for simple validation without context/RBAC."""
    return validate_proposal(proposal, context={}, allowed_agents=None)
from dir_runtime.logging_utils import log_with_dfid
from dir_runtime.news_generator import NewsGenerator
from dir_runtime.quote_generator import QuoteGenerator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# =============================================================================
# Config
# =============================================================================

INSTRUMENTS = ["BTC-USD", "ETH-USD"]
SIMULATION_TICKS = 20
TICK_INTERVAL_SEC = 0.3
NEWS_EVERY_N_TICKS = 5
MAX_NEWS_EVENTS = 4
QUOTE_SEED = 42
NEWS_SEED = 43
INITIAL_PRICES = {"BTC-USD": 67500.0, "ETH-USD": 3500.0}
NEWS_SCORE_THRESHOLD = 0.6


# =============================================================================
# Reactive agents (EOAM pattern)
# =============================================================================


@dataclass
class ReactiveAgent:
    """Base reactive agent: receives payload, returns PolicyProposal or None."""

    agent_id: str
    scope: Optional[str] = None

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        raise NotImplementedError

    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        return None


class ReactiveInstrumentAgent(ReactiveAgent):
    """Instrument-level agent: reacts to market signals, may propose OPEN_POSITION or HOLD."""

    def __init__(self, instrument: str, initial_price: float = 100.0):
        super().__init__(agent_id=f"instrument_{instrument.replace('-', '_')}", scope=instrument)
        self.instrument = instrument
        self._last_price = initial_price

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        dfid = payload.get("dfid", new_dfid())
        price = payload.get("price", self._last_price)
        trend = payload.get("trend", "neutral")
        volatility = payload.get("volatility", 0.02)
        self._last_price = price

        if trend == "bullish" and volatility < 0.04:
            kind = "OPEN_POSITION"
            confidence = 0.75
        elif volatility > 0.05:
            kind = "HOLD"
            confidence = 0.7
        else:
            kind = "HOLD"
            confidence = 0.8

        log_with_dfid(logger, dfid, logging.INFO, "[%s] %s (trend=%s vol=%.2f)", self.agent_id, kind, trend, volatility)
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=kind,
            params={"instrument": self.instrument, "price": price, "trend": trend},
            confidence=confidence,
        )


class ReactivePositionAgent(ReactiveAgent):
    """Position-level agent: reacts to market, proposes CLOSE / TAKE_PROFIT / ADJUST_STOP / HOLD."""

    def __init__(self, position_id: str, instrument: str, entry_price: float):
        super().__init__(agent_id=f"position_{position_id}", scope=instrument)
        self.position_id = position_id
        self.instrument = instrument
        self.entry_price = entry_price

    def on_observation(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        dfid = payload.get("dfid", new_dfid())
        price = payload.get("price", self.entry_price)
        pnl_pct = (price - self.entry_price) / self.entry_price if self.entry_price else 0

        if pnl_pct < -0.03:
            kind = "CLOSE"
            confidence = 0.95
        elif pnl_pct > 0.05:
            kind = "TAKE_PROFIT"
            confidence = 0.85
        elif pnl_pct < -0.01:
            kind = "ADJUST_STOP"
            confidence = 0.75
        else:
            kind = "HOLD"
            confidence = 0.8

        log_with_dfid(
            logger, dfid, logging.INFO,
            "[%s] %s (pnl=%.2f%%)", self.agent_id, kind, pnl_pct * 100,
        )
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind=kind,
            params={"position_id": self.position_id, "instrument": self.instrument, "pnl_pct": pnl_pct},
            confidence=confidence,
        )


class NewsScoringAgent(ReactiveAgent):
    """Scores news; emits NEWS_QUALIFIED if score above threshold."""

    def __init__(self, score_threshold: float = 0.6):
        super().__init__(agent_id="news_scorer", scope=None)

    def on_news(self, payload: Dict[str, Any]) -> Optional[PolicyProposal]:
        dfid = payload.get("dfid", new_dfid())
        raw_score = payload.get("raw_score", 0.5)
        headline = payload.get("headline", "")[:50]
        if raw_score < NEWS_SCORE_THRESHOLD:
            log_with_dfid(logger, dfid, logging.DEBUG, "[%s] News score %.2f below threshold, skip", self.agent_id, raw_score)
            return None
        log_with_dfid(logger, dfid, logging.INFO, "[%s] NEWS_QUALIFIED score=%.2f: %s", self.agent_id, raw_score, headline)
        return PolicyProposal(
            dfid=dfid,
            agent_id=self.agent_id,
            policy_kind="NEWS_QUALIFIED",
            params={"raw_score": raw_score, "headline": payload.get("headline"), "news_id": payload.get("news_id")},
            confidence=raw_score,
        )


# =============================================================================
# EOAM Orchestrator (observation + news, arbitration, DIM, spawn)
# =============================================================================


@dataclass
class EOAMOrchestrator:
    """Orchestrates EOAM: register agents, emit observation/news, collect proposals, arbitrate, DIM, spawn position agents."""

    bus: EventBus
    priority_matrix: Dict[str, int] = field(default_factory=dict)
    _pending: Dict[str, List[PolicyProposal]] = field(default_factory=dict)
    _position_agents: List[ReactivePositionAgent] = field(default_factory=list)
    _instrument_agents: Dict[str, ReactiveInstrumentAgent] = field(default_factory=dict)
    _next_position_id: int = 1

    def __post_init__(self):
        if not self.priority_matrix:
            self.priority_matrix = {
                "RISK_ALERT": 1,
                "CLOSE": 2,
                "TAKE_PROFIT": 3,
                "ADJUST_STOP": 4,
                "OPEN_POSITION": 5,
                "NEWS_QUALIFIED": 6,
                "HOLD": 10,
            }

    def register_agent(self, agent: ReactiveAgent) -> None:
        """Subscribe agent to OBSERVATION (market signals)."""
        if isinstance(agent, ReactiveInstrumentAgent):
            self._instrument_agents[agent.instrument] = agent
        elif isinstance(agent, ReactivePositionAgent):
            self._position_agents.append(agent)

        def handler(payload: Dict[str, Any]) -> None:
            prop = agent.on_observation(payload)
            if prop:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending:
                    self._pending[dfid] = []
                self._pending[dfid].append(prop)

        self.bus.subscribe(EventType.OBSERVATION, handler, scope=agent.scope)

    def register_news_agent(self, agent: NewsScoringAgent) -> None:
        """Subscribe agent to NEWS."""

        def handler(payload: Dict[str, Any]) -> None:
            prop = agent.on_news(payload)
            if prop:
                dfid = payload.get("dfid", "unknown")
                if dfid not in self._pending:
                    self._pending[dfid] = []
                self._pending[dfid].append(prop)

        self.bus.subscribe(EventType.NEWS, handler, scope=None)

    def emit_observation(self, payload: Dict[str, Any], scope: Optional[str] = None) -> str:
        dfid = payload.get("dfid") or new_dfid()
        payload["dfid"] = dfid
        self.bus.publish(
            EventType.OBSERVATION,
            payload,
            EventMetadata(dfid=dfid, target_scope=scope, source_agent="orchestrator"),
        )
        return dfid

    def emit_news(self, payload: Dict[str, Any]) -> str:
        dfid = payload.get("dfid") or new_dfid()
        payload["dfid"] = dfid
        self.bus.publish(
            EventType.NEWS,
            payload,
            EventMetadata(dfid=dfid, source_agent="news_generator"),
        )
        return dfid

    def arbitrate(self, dfid: str) -> Optional[PolicyProposal]:
        proposals = self._pending.get(dfid, [])
        if not proposals:
            return None

        def prio(p: PolicyProposal) -> int:
            return self.priority_matrix.get(p.policy_kind, 10)
        winner = min(proposals, key=prio)
        log_with_dfid(logger, dfid, logging.INFO, "Arbitration: %d proposals → winner %s from %s", len(proposals), winner.policy_kind, winner.agent_id)
        return winner

    def clear_pending(self, dfid: str) -> None:
        self._pending.pop(dfid, None)

    def spawn_position_agent(self, instrument: str, entry_price: float) -> ReactivePositionAgent:
        """Create and register a new PositionAgent (dynamic agent)."""
        position_id = f"POS_{self._next_position_id}"
        self._next_position_id += 1
        agent = ReactivePositionAgent(position_id=position_id, instrument=instrument, entry_price=entry_price)
        self.register_agent(agent)
        log_with_dfid(logger, "", logging.INFO, "Spawned %s for %s at %.2f", agent.agent_id, instrument, entry_price)
        return agent


# =============================================================================
# Main: run simulation
# =============================================================================


def main() -> None:
    print("=" * 70)
    print("EOAM Live Simulation - Quotes, News, Scoring, Dynamic Position Agents")
    print("=" * 70)

    bus = create_event_bus(backend="memory")
    orch = EOAMOrchestrator(bus=bus)

    # Instrument agents (class-level)
    for inst in INSTRUMENTS:
        agent = ReactiveInstrumentAgent(inst, initial_price=INITIAL_PRICES.get(inst, 1000.0))
        orch.register_agent(agent)

    # News scoring agent
    news_agent = NewsScoringAgent(score_threshold=NEWS_SCORE_THRESHOLD)
    orch.register_news_agent(news_agent)

    # One quote generator per instrument (we'll round-robin or use first for simplicity; plan allows one or many)
    generators: List[QuoteGenerator] = []
    for inst in INSTRUMENTS:
        gen = QuoteGenerator(
            instrument=inst,
            initial_price=INITIAL_PRICES.get(inst, 1000.0),
            volatility=0.02,
            seed=QUOTE_SEED + len(generators),
            tick_interval_sec=0,
        )
        generators.append(gen)

    news_gen = NewsGenerator(
        instruments=INSTRUMENTS,
        seed=NEWS_SEED,
        interval_sec=1.0,
        random_interval=False,
    )

    tick_count = 0
    news_count = 0

    for tick_idx in range(SIMULATION_TICKS):
        # Round-robin instrument for tick
        inst_index = tick_count % len(INSTRUMENTS)
        quote_gen = generators[inst_index]
        tick_payload = quote_gen.next_tick().to_payload()
        scope = tick_payload["instrument"]
        dfid = orch.emit_observation(tick_payload, scope=scope)

        winner = orch.arbitrate(dfid)
        orch.clear_pending(dfid)

        if winner:
            result, reason = validate(winner)
            log_with_dfid(logger, dfid, logging.INFO, "DIM: %s %s", result, reason)
            if result == "ACCEPT":
                if winner.policy_kind == "OPEN_POSITION":
                    entry_price = winner.params.get("price", tick_payload.get("price"))
                    orch.spawn_position_agent(winner.params["instrument"], entry_price)
                else:
                    log_with_dfid(logger, dfid, logging.INFO, "Mock execution: %s", winner.policy_kind)

        tick_count += 1

        # Inject news every NEWS_EVERY_N_TICKS
        if tick_count % NEWS_EVERY_N_TICKS == 0 and news_count < MAX_NEWS_EVENTS:
            news_payload = next(news_gen.news_payloads(max_events=1, sleep_between=False))
            news_dfid = orch.emit_news(news_payload)
            news_winner = orch.arbitrate(news_dfid)
            orch.clear_pending(news_dfid)
            if news_winner:
                result, _ = validate(news_winner)
                log_with_dfid(logger, news_dfid, logging.INFO, "News cycle winner: %s DIM=%s", news_winner.policy_kind, result)
            news_count += 1

        if TICK_INTERVAL_SEC > 0:
            time.sleep(TICK_INTERVAL_SEC)

    print("\n" + "=" * 70)
    print("[SUMMARY] EOAM Live Simulation")
    print("=" * 70)
    print(f"  Ticks: {tick_count}, News events: {news_count}")
    print(f"  Position agents spawned: {len(orch._position_agents)}")
    print(f"  Bus events: {bus.event_count}")


if __name__ == "__main__":
    main()

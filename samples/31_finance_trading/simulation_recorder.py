"""
SimulationRecorder - collects ticks, decisions, and positions for HTML report.

Records all data needed to reconstruct the full decision lifecycle and
generate charts with price quotes and decision points.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TickRecord:
    """Single tick (market observation) for chart data."""

    tick_index: int
    instrument: str
    price: float
    timestamp: str
    dfid: str
    trend: str = "neutral"
    volatility: float = 0.0


@dataclass
class SimDecisionRecord:
    """Single decision event for report (agent proposal + DIM result)."""

    tick_index: int
    dfid: str
    parent_dfid: Optional[str]
    agent_id: str
    policy_kind: str
    justification: Optional[str]
    dim_result: str
    dim_reason: str
    explain_narrative: Optional[str]
    explain_signals: List[str]
    explain_risks: List[str]
    explain_opportunities: List[str]
    instrument: Optional[str]
    price: Optional[float]
    event_type: str  # "observation" | "news"
    instruments_affected: List[str] = field(default_factory=list)  # For NEWS_QUALIFIED


@dataclass
class PositionRecord:
    """Position lifecycle: spawn from news, decisions (HOLD/REDUCE/CLOSE)."""

    position_id: str
    instrument: str
    entry_tick: int
    entry_price: float
    parent_dfid: Optional[str]
    news_headline: Optional[str]
    lifecycle_events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SimulationRecorder:
    """Collects simulation data for HTML report generation."""

    ticks: List[TickRecord] = field(default_factory=list)
    decisions: List[SimDecisionRecord] = field(default_factory=list)
    positions: List[PositionRecord] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory=list)

    def record_tick(
        self,
        tick_index: int,
        payload: Dict[str, Any],
        dfid: str,
    ) -> None:
        """Record one market tick."""
        self.ticks.append(
            TickRecord(
                tick_index=tick_index,
                instrument=payload.get("instrument", ""),
                price=payload.get("price", 0.0),
                timestamp=payload.get("timestamp", ""),
                dfid=dfid,
                trend=payload.get("trend", "neutral"),
                volatility=payload.get("volatility", 0.0),
            )
        )

    def record_decision(
        self,
        tick_index: int,
        proposal: Any,
        dim_result: str,
        dim_reason: str,
        event_type: str = "observation",
    ) -> None:
        """Record a decision (winner proposal + DIM result)."""
        params = getattr(proposal, "params", {}) or {}
        instruments_affected = params.get("instruments_affected", [])
        instrument = params.get("instrument")
        if not instrument and instruments_affected:
            instrument = instruments_affected[0] if instruments_affected else None
        self.decisions.append(
            SimDecisionRecord(
                tick_index=tick_index,
                dfid=getattr(proposal, "dfid", ""),
                parent_dfid=params.get("parent_dfid"),
                agent_id=getattr(proposal, "agent_id", ""),
                policy_kind=getattr(proposal, "policy_kind", ""),
                justification=getattr(proposal, "justification", None),
                dim_result=dim_result,
                dim_reason=dim_reason,
                explain_narrative=params.get("explain_narrative"),
                explain_signals=params.get("explain_signals", []),
                explain_risks=params.get("explain_risks", []),
                explain_opportunities=params.get("explain_opportunities", []),
                instrument=instrument,
                price=params.get("price"),
                event_type=event_type,
                instruments_affected=instruments_affected,
            )
        )

    def record_position_spawn(
        self,
        position_id: str,
        instrument: str,
        entry_tick: int,
        entry_price: float,
        parent_dfid: Optional[str] = None,
        news_headline: Optional[str] = None,
    ) -> None:
        """Record spawn of instrument manager / position agent."""
        self.positions.append(
            PositionRecord(
                position_id=position_id,
                instrument=instrument,
                entry_tick=entry_tick,
                entry_price=entry_price,
                parent_dfid=parent_dfid,
                news_headline=news_headline,
                lifecycle_events=[],
            )
        )

    def record_position_decision(
        self,
        position_id: str,
        tick_index: int,
        policy_kind: str,
        price: float,
        justification: Optional[str] = None,
    ) -> None:
        """Record a decision by a position/instrument manager agent."""
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.lifecycle_events.append(
                    {
                        "tick_index": tick_index,
                        "policy_kind": policy_kind,
                        "price": price,
                        "justification": justification,
                    }
                )
                break

    def record_news(self, payload: Dict[str, Any], dfid: str) -> None:
        """Record a news event for report context."""
        self.news_events.append(
            {
                "dfid": dfid,
                "headline": payload.get("headline", ""),
                "sentiment": payload.get("sentiment"),
                "instruments_affected": payload.get("instruments_affected", []),
                "raw_score": payload.get("raw_score"),
            }
        )

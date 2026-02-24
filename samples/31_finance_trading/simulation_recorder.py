"""
SimulationRecorder - collects ticks, decisions, and positions for HTML report.

Records all data needed to reconstruct the full decision lifecycle and
generate charts with price quotes and decision points.

Data is stored both in memory (for HTML report generation) and optionally
in SQLite database (for persistent storage and analysis).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from .simulation_database import SimulationDatabase
except ImportError:
    from simulation_database import SimulationDatabase


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
@dataclass
class PositionRecord:
    """Position lifecycle: spawn from news with exposure tracking, decisions (HOLD/REDUCE/CLOSE)."""

    position_id: str
    instrument: str
    entry_tick: int
    entry_price: float
    initial_exposure: float
    current_exposure: float
    quantity: float
    parent_dfid: Optional[str]
    news_headline: Optional[str]
    lifecycle_events: List[Dict[str, Any]] = field(default_factory=list)
    close_tick: Optional[int] = None
    close_price: Optional[float] = None
    close_reason: Optional[str] = None


@dataclass
class SimulationRecorder:
    """Collects simulation data for HTML report generation and SQLite persistence."""

    ticks: List[TickRecord] = field(default_factory=list)
    decisions: List[SimDecisionRecord] = field(default_factory=list)
    positions: List[PositionRecord] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory=list)
    db_path: Optional[str] = None
    db: Optional[SimulationDatabase] = field(default=None, init=False, repr=False)
    
    def __post_init__(self) -> None:
        """Initialize database connection if db_path is provided."""
        if self.db_path:
            self.db = SimulationDatabase(self.db_path)
            self.db.connect()
    
    def start_simulation(self, config: Dict[str, Any]) -> str:
        """Start a new simulation run and return simulation ID."""
        if self.db:
            return self.db.start_simulation(config)
        return "no-db"
    
    def complete_simulation(self, status: str = "completed", error_message: Optional[str] = None) -> None:
        """Mark simulation as completed and close database connection."""
        if self.db:
            self.db.complete_simulation(status, error_message)
            self.db.close()

    def record_tick(
        self,
        tick_index: int,
        payload: Dict[str, Any],
        dfid: str,
    ) -> None:
        """Record one market tick (memory + database)."""
        tick = TickRecord(
            tick_index=tick_index,
            instrument=payload.get("instrument", ""),
            price=payload.get("price", 0.0),
            timestamp=payload.get("timestamp", ""),
            dfid=dfid,
            trend=payload.get("trend", "neutral"),
            volatility=payload.get("volatility", 0.0),
        )
        self.ticks.append(tick)
        
        # Also save to database
        if self.db:
            self.db.insert_tick(
                tick_index=tick.tick_index,
                instrument=tick.instrument,
                price=tick.price,
                timestamp=tick.timestamp,
                dfid=tick.dfid,
                trend=tick.trend,
                volatility=tick.volatility,
            )

    def record_decision(
        self,
        tick_index: int,
        proposal: Any,
        dim_result: str,
        dim_reason: str,
        event_type: str = "observation",
    ) -> None:
        """Record a decision (winner proposal + DIM result) (memory + database)."""
        params = getattr(proposal, "params", {}) or {}
        instruments_affected = params.get("instruments_affected", [])
        instrument = params.get("instrument")
        if not instrument and instruments_affected:
            instrument = instruments_affected[0] if instruments_affected else None
        
        decision = SimDecisionRecord(
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
        self.decisions.append(decision)
        
        # Also save to database
        if self.db:
            self.db.insert_decision(
                tick_index=decision.tick_index,
                dfid=decision.dfid,
                parent_dfid=decision.parent_dfid,
                agent_id=decision.agent_id,
                policy_kind=decision.policy_kind,
                justification=decision.justification,
                dim_result=decision.dim_result,
                dim_reason=decision.dim_reason,
                explain_narrative=decision.explain_narrative,
                explain_signals=decision.explain_signals,
                explain_risks=decision.explain_risks,
                explain_opportunities=decision.explain_opportunities,
                instrument=decision.instrument,
                price=decision.price,
                event_type=decision.event_type,
                instruments_affected=decision.instruments_affected,
            )

    def record_position_spawn(
        self,
        position_id: str,
        instrument: str,
        entry_tick: int,
        entry_price: float,
        initial_exposure: float,
        quantity: float,
        parent_dfid: Optional[str] = None,
        news_headline: Optional[str] = None,
    ) -> None:
        """Record spawn of position agent with exposure tracking (memory + database)."""
        position = PositionRecord(
            position_id=position_id,
            instrument=instrument,
            entry_tick=entry_tick,
            entry_price=entry_price,
            initial_exposure=initial_exposure,
            current_exposure=initial_exposure,
            quantity=quantity,
            parent_dfid=parent_dfid,
            news_headline=news_headline,
            lifecycle_events=[],
        )
        self.positions.append(position)
        
        # Also save to database
        if self.db:
            self.db.insert_position(
                position_id=position.position_id,
                instrument=position.instrument,
                entry_tick=position.entry_tick,
                entry_price=position.entry_price,
                initial_exposure=position.initial_exposure,
                quantity=position.quantity,
                parent_dfid=position.parent_dfid,
                news_headline=position.news_headline,
            )

    def record_position_decision(
        self,
        position_id: str,
        tick_index: int,
        policy_kind: str,
        price: float,
        justification: Optional[str] = None,
    ) -> None:
        """Record a decision by a position/instrument manager agent (memory + database)."""
        event = {
            "tick_index": tick_index,
            "policy_kind": policy_kind,
            "price": price,
            "justification": justification,
        }
        
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.lifecycle_events.append(event)
                break
        
        # Also save to database
        if self.db:
            self.db.insert_position_lifecycle_event(
                position_id=position_id,
                tick_index=tick_index,
                policy_kind=policy_kind,
                price=price,
                justification=justification,
            )
    
    def close_position(
        self,
        position_id: str,
        close_tick: int,
        close_price: float,
        close_reason: str,
    ) -> None:
        """Mark position as closed (memory + database)."""
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.close_tick = close_tick
                pos.close_price = close_price
                pos.close_reason = close_reason
                pos.current_exposure = 0.0
                break
        
        # Also save to database
        if self.db:
            self.db.close_position(
                position_id=position_id,
                close_tick=close_tick,
                close_price=close_price,
                close_reason=close_reason,
            )
    
    def update_position_exposure(
        self,
        position_id: str,
        new_exposure: float,
    ) -> None:
        """Update current exposure for a position (after REDUCE)."""
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.current_exposure = new_exposure
                break
        
        # Also save to database
        if self.db:
            self.db.update_position_exposure(
                position_id=position_id,
                new_exposure=new_exposure,
            )

    def record_news(self, payload: Dict[str, Any], dfid: str) -> None:
        """Record a news event for report context (memory + database)."""
        news_event = {
            "dfid": dfid,
            "headline": payload.get("headline", ""),
            "sentiment": payload.get("sentiment"),
            "instruments_affected": payload.get("instruments_affected", []),
            "raw_score": payload.get("raw_score"),
        }
        self.news_events.append(news_event)
        
        # Also save to database
        if self.db:
            self.db.insert_news_event(
                dfid=dfid,
                headline=news_event["headline"],
                sentiment=news_event["sentiment"],
                instruments_affected=news_event["instruments_affected"],
                raw_score=news_event["raw_score"],
            )

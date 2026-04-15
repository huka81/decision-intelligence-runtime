"""
SimulationRecorder - collects ticks, decisions, and positions for HTML report.

Records all data needed to reconstruct the full decision lifecycle and
generate charts with price quotes and decision points.

Data is stored both in memory (for HTML report generation) and optionally
in SQLite database (for persistent storage and analysis) via dir_core's
DecisionAuditStorage.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage import StorageBundle


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
    instruments_affected: List[str] = field(default_factory=list)


@dataclass
class PositionRecord:
    """Position lifecycle: spawn from news with exposure tracking, decisions."""
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
    """Collects simulation data for HTML report generation and SQLite persistence via DIR canonical model."""
    ticks: List[TickRecord] = field(default_factory=list)
    decisions: List[SimDecisionRecord] = field(default_factory=list)
    positions: List[PositionRecord] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory=list)
    bundle: Optional[StorageBundle] = field(default=None, repr=False)
    simulation_id: str = field(default="no-db")

    def start_simulation(self, config: Dict[str, Any]) -> str:
        """Start a new simulation run and return simulation ID."""
        if not self.bundle:
            return "no-db"
        timestamp = datetime.now(timezone.utc).isoformat()
        config_str = json.dumps(config, sort_keys=True)
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
        self.simulation_id = f"sim_{timestamp.replace(':', '-').replace('.', '-')}_{config_hash[:8]}"

        self.bundle.decision_audit.record(
            self.simulation_id,
            "SIMULATION_START",
            details={
                "simulation_id": self.simulation_id,
                "config_hash": config_hash,
                "simulation_ticks": config.get("simulation", {}).get("simulation_ticks"),
            }
        )
        return self.simulation_id

    def complete_simulation(self, status: str = "completed", error_message: Optional[str] = None) -> None:
        """Mark simulation as completed in audit log."""
        if self.bundle:
            self.bundle.decision_audit.record(
                self.simulation_id,
                "SIMULATION_END",
                details={
                    "simulation_id": self.simulation_id,
                    "status": status,
                    "error_message": error_message,
                }
            )

    def record_tick(
        self,
        tick_index: int,
        payload: Dict[str, Any],
        dfid: str,
    ) -> None:
        """Record one market tick."""
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
        
        if self.bundle:
            self.bundle.decision_audit.record(
                dfid,
                "MARKET_TICK",
                details={
                    "simulation_id": self.simulation_id,
                    "tick_index": tick_index,
                    "instrument": tick.instrument,
                    "price": tick.price,
                    "trend": tick.trend,
                    "volatility": tick.volatility,
                    "timestamp": tick.timestamp,
                }
            )

    def record_decision(
        self,
        tick_index: int,
        proposal: Any,
        dim_result: str,
        dim_reason: str,
        event_type: str = "observation",
    ) -> None:
        """Record a decision."""
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
        
        if self.bundle:
            self.bundle.decision_audit.record(
                decision.dfid,
                "AGENT_DECISION",
                details={
                    "simulation_id": self.simulation_id,
                    "tick_index": tick_index,
                    "parent_dfid": decision.parent_dfid,
                    "agent_id": decision.agent_id,
                    "policy_kind": decision.policy_kind,
                    "justification": decision.justification,
                    "dim_result": decision.dim_result,
                    "dim_reason": decision.dim_reason,
                    "explain_narrative": decision.explain_narrative,
                    "explain_signals": decision.explain_signals,
                    "explain_risks": decision.explain_risks,
                    "explain_opportunities": decision.explain_opportunities,
                    "instrument": decision.instrument,
                    "price": decision.price,
                    "event_type": decision.event_type,
                    "instruments_affected": decision.instruments_affected,
                }
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
        
        if self.bundle:
            self.bundle.decision_audit.record(
                parent_dfid or self.simulation_id,
                "POSITION_SPAWNED",
                details={
                    "simulation_id": self.simulation_id,
                    "position_id": position_id,
                    "instrument": instrument,
                    "entry_tick": entry_tick,
                    "entry_price": entry_price,
                    "initial_exposure": initial_exposure,
                    "quantity": quantity,
                    "news_headline": news_headline,
                }
            )

    def record_position_decision(
        self,
        position_id: str,
        tick_index: int,
        policy_kind: str,
        price: float,
        justification: Optional[str] = None,
    ) -> None:
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
        
        if self.bundle:
            self.bundle.decision_audit.record(
                self.simulation_id,
                "POSITION_EVENT",
                details={
                    "simulation_id": self.simulation_id,
                    "position_id": position_id,
                    "tick_index": tick_index,
                    "policy_kind": policy_kind,
                    "price": price,
                    "justification": justification,
                }
            )
    
    def close_position(
        self,
        position_id: str,
        close_tick: int,
        close_price: float,
        close_reason: str,
    ) -> None:
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.close_tick = close_tick
                pos.close_price = close_price
                pos.close_reason = close_reason
                pos.current_exposure = 0.0
                break
        
        if self.bundle:
            self.bundle.decision_audit.record(
                self.simulation_id,
                "POSITION_CLOSED",
                details={
                    "simulation_id": self.simulation_id,
                    "position_id": position_id,
                    "close_tick": close_tick,
                    "close_price": close_price,
                    "close_reason": close_reason,
                }
            )
    
    def update_position_exposure(
        self,
        position_id: str,
        new_exposure: float,
    ) -> None:
        for pos in self.positions:
            if pos.position_id == position_id:
                pos.current_exposure = new_exposure
                break
        
        if self.bundle:
            self.bundle.decision_audit.record(
                self.simulation_id,
                "POSITION_EXPOSURE_UPDATED",
                details={
                    "simulation_id": self.simulation_id,
                    "position_id": position_id,
                    "new_exposure": new_exposure,
                }
            )

    def record_news(self, payload: Dict[str, Any], dfid: str) -> None:
        news_event = {
            "dfid": dfid,
            "headline": payload.get("headline", ""),
            "sentiment": payload.get("sentiment"),
            "instruments_affected": payload.get("instruments_affected", []),
            "raw_score": payload.get("raw_score"),
        }
        self.news_events.append(news_event)
        
        if self.bundle:
            self.bundle.decision_audit.record(
                dfid,
                "NEWS_GENERATED",
                details={
                    "simulation_id": self.simulation_id,
                    **news_event
                }
            )

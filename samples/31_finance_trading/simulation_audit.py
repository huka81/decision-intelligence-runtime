"""
Finance trading sample — simulation events via canonical DecisionAuditStorage.

All runtime persistence goes through ``bundle.decision_audit`` on a
:class:`dir_core.storage.StorageBundle` (from ``sqlite_storage``,
``build_repository``, etc.). No parallel in-memory collector during the run.

Rows land in ``decision_audit_events``. Column ``dfid`` is the flow id (often a
UUID for ticks); ``simulation_id`` is stored inside ``detail_json`` / ``details``.
To list one run in PostgreSQL, filter
``detail_json->>'simulation_id'``, not ``dfid LIKE 'sim_%'`` (that only shows
start/end rows).

``hydrate_report_state_from_audit`` rebuilds report-facing structures from
``all_events_chronological()`` for HTML generation only.
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
    event_type: str
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
class SimulationReportState:
    """In-memory view of one simulation for HTML report (loaded from audit log)."""
    simulation_id: str
    ticks: List[TickRecord] = field(default_factory=list)
    decisions: List[SimDecisionRecord] = field(default_factory=list)
    positions: List[PositionRecord] = field(default_factory=list)
    news_events: List[Dict[str, Any]] = field(default_factory=list)


def count_decision_audit_rows_for_simulation(
    bundle: StorageBundle,
    simulation_id: str,
) -> int:
    """Count audit rows for *simulation_id* (value lives in ``details`` / ``detail_json``).

    MARKET_TICK and most events use the observation DFID in column ``dfid``; the
    run id is duplicated in ``details['simulation_id']``. Filtering only
    ``WHERE dfid LIKE 'sim_%'`` typically shows just SIMULATION_START / END.

    PostgreSQL: runs ``COUNT(*)`` with ``detail_json->>'simulation_id'``.
    SQLite / memory: scans ``all_events_chronological()`` in process.
    """
    da = bundle.decision_audit
    conn = getattr(da, "_conn", None)
    if conn is not None:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM decision_audit_events
                WHERE COALESCE(detail_json->>'simulation_id', '') = %s
                """,
                (simulation_id,),
            )
            row = cur.fetchone()
        return int(row[0]) if row else 0

    return sum(
        1
        for e in bundle.decision_audit.all_events_chronological()
        if e.get("details", {}).get("simulation_id") == simulation_id
    )


def start_simulation_audit(bundle: StorageBundle, config: Dict[str, Any]) -> str:
    """Emit SIMULATION_START and return the new simulation_id."""
    timestamp = datetime.now(timezone.utc).isoformat()
    config_str = json.dumps(config, sort_keys=True)
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
    simulation_id = (
        f"sim_{timestamp.replace(':', '-').replace('.', '-')}_{config_hash[:8]}"
    )
    bundle.decision_audit.record(
        simulation_id,
        "SIMULATION_START",
        details={
            "simulation_id": simulation_id,
            "config_hash": config_hash,
            "simulation_ticks": config.get("simulation", {}).get("simulation_ticks"),
        },
    )
    return simulation_id


def complete_simulation_audit(
    bundle: StorageBundle,
    simulation_id: str,
    status: str = "completed",
    error_message: Optional[str] = None,
) -> None:
    bundle.decision_audit.record(
        simulation_id,
        "SIMULATION_END",
        details={
            "simulation_id": simulation_id,
            "status": status,
            "error_message": error_message,
        },
    )


def record_market_tick(
    bundle: StorageBundle,
    simulation_id: str,
    tick_index: int,
    payload: Dict[str, Any],
    dfid: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "MARKET_TICK",
        details={
            "simulation_id": simulation_id,
            "tick_index": tick_index,
            "instrument": payload.get("instrument", ""),
            "price": payload.get("price", 0.0),
            "trend": payload.get("trend", "neutral"),
            "volatility": payload.get("volatility", 0.0),
            "timestamp": payload.get("timestamp", ""),
        },
    )


def record_agent_decision(
    bundle: StorageBundle,
    simulation_id: str,
    tick_index: int,
    proposal: Any,
    dim_result: str,
    dim_reason: str,
    event_type: str = "observation",
) -> None:
    params = getattr(proposal, "params", {}) or {}
    instruments_affected = params.get("instruments_affected", [])
    instrument = params.get("instrument")
    if not instrument and instruments_affected:
        instrument = instruments_affected[0] if instruments_affected else None
    dfid = getattr(proposal, "dfid", "")
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        details={
            "simulation_id": simulation_id,
            "tick_index": tick_index,
            "parent_dfid": params.get("parent_dfid"),
            "agent_id": getattr(proposal, "agent_id", ""),
            "policy_kind": getattr(proposal, "policy_kind", ""),
            "justification": getattr(proposal, "justification", None),
            "dim_result": dim_result,
            "dim_reason": dim_reason,
            "explain_narrative": params.get("explain_narrative"),
            "explain_signals": params.get("explain_signals", []),
            "explain_risks": params.get("explain_risks", []),
            "explain_opportunities": params.get("explain_opportunities", []),
            "instrument": instrument,
            "price": params.get("price"),
            "event_type": event_type,
            "instruments_affected": instruments_affected,
        },
    )


def record_position_spawned(
    bundle: StorageBundle,
    simulation_id: str,
    position_id: str,
    instrument: str,
    entry_tick: int,
    entry_price: float,
    initial_exposure: float,
    quantity: float,
    parent_dfid: Optional[str] = None,
    news_headline: Optional[str] = None,
) -> None:
    bundle.decision_audit.record(
        parent_dfid or simulation_id,
        "POSITION_SPAWNED",
        details={
            "simulation_id": simulation_id,
            "position_id": position_id,
            "instrument": instrument,
            "entry_tick": entry_tick,
            "entry_price": entry_price,
            "initial_exposure": initial_exposure,
            "quantity": quantity,
            "news_headline": news_headline,
        },
    )


def record_position_event(
    bundle: StorageBundle,
    simulation_id: str,
    position_id: str,
    tick_index: int,
    policy_kind: str,
    price: float,
    justification: Optional[str] = None,
) -> None:
    bundle.decision_audit.record(
        simulation_id,
        "POSITION_EVENT",
        details={
            "simulation_id": simulation_id,
            "position_id": position_id,
            "tick_index": tick_index,
            "policy_kind": policy_kind,
            "price": price,
            "justification": justification,
        },
    )


def record_position_closed(
    bundle: StorageBundle,
    simulation_id: str,
    position_id: str,
    close_tick: int,
    close_price: float,
    close_reason: str,
) -> None:
    bundle.decision_audit.record(
        simulation_id,
        "POSITION_CLOSED",
        details={
            "simulation_id": simulation_id,
            "position_id": position_id,
            "close_tick": close_tick,
            "close_price": close_price,
            "close_reason": close_reason,
        },
    )


def record_position_exposure_updated(
    bundle: StorageBundle,
    simulation_id: str,
    position_id: str,
    new_exposure: float,
) -> None:
    bundle.decision_audit.record(
        simulation_id,
        "POSITION_EXPOSURE_UPDATED",
        details={
            "simulation_id": simulation_id,
            "position_id": position_id,
            "new_exposure": new_exposure,
        },
    )


def record_news_generated(
    bundle: StorageBundle,
    simulation_id: str,
    payload: Dict[str, Any],
    dfid: str,
) -> None:
    news_event = {
        "dfid": dfid,
        "headline": payload.get("headline", ""),
        "sentiment": payload.get("sentiment"),
        "instruments_affected": payload.get("instruments_affected", []),
        "raw_score": payload.get("raw_score"),
    }
    bundle.decision_audit.record(
        dfid,
        "NEWS_GENERATED",
        details={"simulation_id": simulation_id, **news_event},
    )


def hydrate_report_state_from_audit(
    events: List[Dict[str, Any]],
    simulation_id: str,
) -> SimulationReportState:
    """Rebuild :class:`SimulationReportState` from chronological audit rows."""
    state = SimulationReportState(simulation_id=simulation_id)
    for row in events:
        d = row.get("details", {})
        if d.get("simulation_id") != simulation_id:
            continue
        ev_type = row.get("event")
        if ev_type == "MARKET_TICK":
            state.ticks.append(
                TickRecord(
                    tick_index=d.get("tick_index", 0),
                    instrument=d.get("instrument", ""),
                    price=d.get("price", 0.0),
                    timestamp=d.get("timestamp", row["timestamp"]),
                    dfid=row["dfid"],
                    trend=d.get("trend", "neutral"),
                    volatility=d.get("volatility", 0.0),
                )
            )
        elif ev_type == "AGENT_DECISION":
            state.decisions.append(
                SimDecisionRecord(
                    tick_index=d.get("tick_index", 0),
                    dfid=row["dfid"],
                    parent_dfid=d.get("parent_dfid"),
                    agent_id=d.get("agent_id", ""),
                    policy_kind=d.get("policy_kind", ""),
                    justification=d.get("justification"),
                    dim_result=d.get("dim_result", ""),
                    dim_reason=d.get("dim_reason", ""),
                    explain_narrative=d.get("explain_narrative"),
                    explain_signals=d.get("explain_signals", []),
                    explain_risks=d.get("explain_risks", []),
                    explain_opportunities=d.get("explain_opportunities", []),
                    instrument=d.get("instrument"),
                    price=d.get("price"),
                    event_type=d.get("event_type", ""),
                    instruments_affected=d.get("instruments_affected", []),
                )
            )
        elif ev_type == "POSITION_SPAWNED":
            state.positions.append(
                PositionRecord(
                    position_id=d.get("position_id", ""),
                    instrument=d.get("instrument", ""),
                    entry_tick=d.get("entry_tick", 0),
                    entry_price=d.get("entry_price", 0.0),
                    initial_exposure=d.get("initial_exposure", 0.0),
                    current_exposure=d.get("initial_exposure", 0.0),
                    quantity=d.get("quantity", 0.0),
                    parent_dfid=d.get("parent_dfid") or row["dfid"],
                    news_headline=d.get("news_headline"),
                    lifecycle_events=[],
                )
            )
        elif ev_type == "POSITION_EVENT":
            for p in state.positions:
                if p.position_id == d.get("position_id"):
                    p.lifecycle_events.append(
                        {
                            "tick_index": d.get("tick_index"),
                            "policy_kind": d.get("policy_kind"),
                            "price": d.get("price"),
                            "justification": d.get("justification"),
                        }
                    )
                    break
        elif ev_type == "POSITION_CLOSED":
            for p in state.positions:
                if p.position_id == d.get("position_id"):
                    p.close_tick = d.get("close_tick")
                    p.close_price = d.get("close_price")
                    p.close_reason = d.get("close_reason")
                    p.current_exposure = 0.0
                    break
        elif ev_type == "POSITION_EXPOSURE_UPDATED":
            for p in state.positions:
                if p.position_id == d.get("position_id"):
                    p.current_exposure = d.get("new_exposure", 0.0)
                    break
        elif ev_type == "NEWS_GENERATED":
            state.news_events.append(
                {
                    "dfid": row["dfid"],
                    "headline": d.get("headline", ""),
                    "sentiment": d.get("sentiment"),
                    "instruments_affected": d.get("instruments_affected", []),
                    "raw_score": d.get("raw_score"),
                }
            )
    return state

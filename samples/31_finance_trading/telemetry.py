"""
Finance trading sample — telemetry helpers for ``AuditStore`` / ``decision_audit_events``.

Thin wrappers around :meth:`AuditStore.record` plus report hydration from
``all_events_chronological()``. No parallel in-memory collector during the run.

Rows land in ``decision_audit_events``. Column ``dfid`` is the flow id (often a
UUID for ticks); ``simulation_id`` is stored inside ``detail_json`` / ``details``.
The run root uses ``root_dfid = simulation_id`` for all child observation and
news flows. Filter PostgreSQL with ``detail_json->>'simulation_id'``, not
``dfid LIKE 'sim_%'`` (that only shows start/end rows).

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
from dir_core.storage.base import AuditStore


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


def _governance_agents(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not config:
        return []
    rows: List[Dict[str, Any]] = []
    for a in config.get("agents") or []:
        c = a.get("contract") or {}
        rows.append(
            {
                "agent_id": a.get("agent_id"),
                "type": a.get("type"),
                "role": c.get("role"),
                "priority": a.get("priority"),
            }
        )
    return rows


def _detail_base(
    simulation_id: str,
    extra: Optional[Dict[str, Any]] = None,
    *,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "correlation_id": simulation_id,
    }
    if causation_id:
        out["causation_id"] = causation_id
    if extra:
        out.update(extra)
    return out


def _record(
    audit: AuditStore,
    dfid: str,
    event: str,
    simulation_id: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    root_dfid: Optional[str] = None,
    agent_id: Optional[str] = None,
    step_id: str = "",
    state: str = "",
    severity: str = "INFO",
    causation_id: Optional[str] = None,
) -> None:
    merged = _detail_base(simulation_id, details, causation_id=causation_id)
    audit.record(
        dfid,
        event,
        step_id=step_id,
        state=state,
        details=merged,
        root_dfid=root_dfid or simulation_id,
        agent_id=agent_id,
        severity=severity,
    )


def count_decision_audit_rows_for_simulation(
    audit: AuditStore,
    simulation_id: str,
    *,
    bundle: Optional[StorageBundle] = None,
) -> int:
    """Count audit rows for *simulation_id* (value lives in ``details`` / ``detail_json``)."""
    da = bundle.decision_audit if bundle is not None else None
    if da is None:
        try:
            da = audit._decision_audit  # type: ignore[attr-defined]
        except AttributeError:
            da = None
    conn = getattr(da, "_conn", None) if da is not None else None
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
        for e in audit.all_events_chronological()
        if e.get("details", {}).get("simulation_id") == simulation_id
    )


def record_simulation_start(
    audit: AuditStore,
    config: Dict[str, Any],
    *,
    llm_backend: str = "",
) -> str:
    """Emit SIMULATION_START and return the new simulation_id (root flow)."""
    timestamp = datetime.now(timezone.utc).isoformat()
    config_str = json.dumps(config, sort_keys=True)
    config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]
    simulation_id = (
        f"sim_{timestamp.replace(':', '-').replace('.', '-')}_{config_hash[:8]}"
    )
    sim = config.get("simulation", {}) or {}
    details: Dict[str, Any] = {
        "config_hash": config_hash,
        "simulation_ticks": sim.get("simulation_ticks"),
        "topology": "A-EOAM",
        "sample": "31_finance_trading",
        "started_at": timestamp,
        "agents": _governance_agents(config),
        "seeds": sim.get("seeds", {}),
    }
    if llm_backend:
        details["llm_backend"] = llm_backend
    _record(
        audit,
        simulation_id,
        "SIMULATION_START",
        simulation_id,
        details=details,
        root_dfid=simulation_id,
        state="CREATED",
    )
    return simulation_id


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str = "completed",
    error_message: Optional[str] = None,
    elapsed_seconds: Optional[float] = None,
    tick_count: int = 0,
    news_count: int = 0,
) -> None:
    details: Dict[str, Any] = {
        "status": status,
        "error_message": error_message,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "tick_count": tick_count,
        "news_count": news_count,
    }
    if elapsed_seconds is not None:
        details["elapsed_seconds"] = elapsed_seconds
    _record(
        audit,
        simulation_id,
        "SIMULATION_END",
        simulation_id,
        details=details,
        root_dfid=simulation_id,
        state="COMPLETED" if status == "completed" else "FAILED",
        severity="ERROR" if status not in ("completed", "ok") else "INFO",
    )


# Backward-compatible aliases
start_simulation_audit = record_simulation_start
complete_simulation_audit = record_simulation_end


def record_flow_transition(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    from_status: str,
    to_status: str,
) -> None:
    """Append lifecycle history with lineage ``root_dfid = simulation_id``."""
    bundle.lifecycle.record_transition(
        dfid,
        from_status,
        to_status,
        root_dfid=simulation_id,
    )


def record_market_tick(
    audit: AuditStore,
    simulation_id: str,
    tick_index: int,
    payload: Dict[str, Any],
    dfid: str,
) -> None:
    _record(
        audit,
        dfid,
        "MARKET_TICK",
        simulation_id,
        details={
            "tick_index": tick_index,
            "instrument": payload.get("instrument", ""),
            "price": payload.get("price", 0.0),
            "trend": payload.get("trend", "neutral"),
            "volatility": payload.get("volatility", 0.0),
            "timestamp": payload.get("timestamp", ""),
        },
        state="RUNNING",
    )


def record_agent_decision(
    audit: AuditStore,
    simulation_id: str,
    tick_index: int,
    proposal: Any,
    dim_result: str,
    dim_reason: str,
    event_type: str = "observation",
    *,
    causation_id: Optional[str] = None,
) -> None:
    params = getattr(proposal, "params", {}) or {}
    instruments_affected = params.get("instruments_affected", [])
    instrument = params.get("instrument")
    if not instrument and instruments_affected:
        instrument = instruments_affected[0] if instruments_affected else None
    dfid = getattr(proposal, "dfid", "")
    agent_id = getattr(proposal, "agent_id", "") or None
    _record(
        audit,
        dfid,
        "AGENT_DECISION",
        simulation_id,
        details={
            "tick_index": tick_index,
            "parent_dfid": params.get("parent_dfid"),
            "agent_id": agent_id or "",
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
        agent_id=agent_id,
        causation_id=causation_id or dfid,
        state=str(dim_result),
    )


def record_position_spawned(
    audit: AuditStore,
    simulation_id: str,
    position_id: str,
    instrument: str,
    entry_tick: int,
    entry_price: float,
    initial_exposure: float,
    quantity: float,
    parent_dfid: Optional[str] = None,
    news_headline: Optional[str] = None,
    *,
    causation_id: Optional[str] = None,
) -> None:
    flow_dfid = parent_dfid or simulation_id
    _record(
        audit,
        flow_dfid,
        "POSITION_SPAWNED",
        simulation_id,
        details={
            "position_id": position_id,
            "instrument": instrument,
            "entry_tick": entry_tick,
            "entry_price": entry_price,
            "initial_exposure": initial_exposure,
            "quantity": quantity,
            "news_headline": news_headline,
            "parent_dfid": parent_dfid,
        },
        causation_id=causation_id or parent_dfid,
        state="RUNNING",
    )


def record_position_event(
    audit: AuditStore,
    simulation_id: str,
    position_id: str,
    tick_index: int,
    policy_kind: str,
    price: float,
    justification: Optional[str] = None,
    *,
    dfid: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid or simulation_id,
        "POSITION_EVENT",
        simulation_id,
        details={
            "position_id": position_id,
            "tick_index": tick_index,
            "policy_kind": policy_kind,
            "price": price,
            "justification": justification,
        },
        causation_id=causation_id,
    )


def record_position_closed(
    audit: AuditStore,
    simulation_id: str,
    position_id: str,
    close_tick: int,
    close_price: float,
    close_reason: str,
    *,
    dfid: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid or simulation_id,
        "POSITION_CLOSED",
        simulation_id,
        details={
            "position_id": position_id,
            "close_tick": close_tick,
            "close_price": close_price,
            "close_reason": close_reason,
        },
        causation_id=causation_id,
        state="COMPLETED",
    )


def record_position_exposure_updated(
    audit: AuditStore,
    simulation_id: str,
    position_id: str,
    new_exposure: float,
    *,
    dfid: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid or simulation_id,
        "POSITION_EXPOSURE_UPDATED",
        simulation_id,
        details={
            "position_id": position_id,
            "new_exposure": new_exposure,
        },
    )


def record_news_generated(
    audit: AuditStore,
    simulation_id: str,
    payload: Dict[str, Any],
    dfid: str,
) -> None:
    _record(
        audit,
        dfid,
        "NEWS_GENERATED",
        simulation_id,
        details={
            "headline": payload.get("headline", ""),
            "sentiment": payload.get("sentiment"),
            "instruments_affected": payload.get("instruments_affected", []),
            "raw_score": payload.get("raw_score"),
        },
        state="CREATED",
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
        ev_type = row.get("event") or row.get("event_type")
        if ev_type == "MARKET_TICK":
            state.ticks.append(
                TickRecord(
                    tick_index=d.get("tick_index", 0),
                    instrument=d.get("instrument", ""),
                    price=d.get("price", 0.0),
                    timestamp=d.get("timestamp", row.get("timestamp", "")),
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

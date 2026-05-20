"""Append-only telemetry via ``AuditStore`` (decision_audit_events)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage.base import AuditStore


def _with_trace(
    simulation_id: str,
    details: Optional[Dict[str, Any]],
    *,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(details or {})
    out.setdefault("simulation_id", simulation_id)
    out.setdefault("correlation_id", simulation_id)
    if causation_id:
        out.setdefault("causation_id", causation_id)
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
    merged = _with_trace(simulation_id, details, causation_id=causation_id)
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


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "topology": "B-SDS",
        "sample": "38_drift_environmental_bidding",
        "started_at": datetime.now(timezone.utc).isoformat(),
        **(details or {}),
    }
    _record(
        audit,
        simulation_id,
        "SIMULATION_START",
        simulation_id,
        details=payload,
        root_dfid=simulation_id,
        state="CREATED",
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    stopped_reason: str,
    details: Optional[Dict[str, Any]] = None,
    elapsed_seconds: Optional[float] = None,
) -> None:
    payload: Dict[str, Any] = {
        "status": status,
        "stopped_reason": stopped_reason,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        **(details or {}),
    }
    if elapsed_seconds is not None:
        payload["elapsed_seconds"] = float(elapsed_seconds)
    sev = "ERROR" if status not in ("ok", "completed") else "INFO"
    end_state = (
        "COMPLETED"
        if status in ("ok", "completed")
        else "FAILED"
    )
    _record(
        audit,
        simulation_id,
        "SIMULATION_END",
        simulation_id,
        details=payload,
        root_dfid=simulation_id,
        state=end_state,
        severity=sev,
    )


def record_context_compiled(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    details: Dict[str, Any],
    agent_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid,
        "CONTEXT_COMPILED",
        simulation_id,
        details=details,
        agent_id=agent_id,
        state="RUNNING",
        causation_id=causation_id or dfid,
    )


def record_policy_proposal(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    details: Dict[str, Any],
    agent_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid,
        "POLICY_PROPOSAL",
        simulation_id,
        details=details,
        agent_id=agent_id,
        state="EMITTED",
        causation_id=causation_id or dfid,
    )


def record_dim_validation(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    verdict: str,
    reason: str,
    agent_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    v = str(verdict).upper()
    sev = "INFO" if v == "ACCEPT" else "WARNING"
    _record(
        audit,
        dfid,
        "DIM_VALIDATION",
        simulation_id,
        details={"reason": reason},
        agent_id=agent_id,
        state=verdict,
        severity=sev,
        causation_id=causation_id or dfid,
    )


def record_cpc_bid_executed(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    cpc_bid_usd: float,
    market_cpc_to_win: float,
    cycle_id: str,
    idempotency_key: str,
    extra: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {
        "cpc_bid_usd": cpc_bid_usd,
        "market_cpc_to_win": market_cpc_to_win,
        "cycle_id": cycle_id,
        "idempotency_key": idempotency_key,
    }
    if extra:
        payload.update(extra)
    _record(
        audit,
        dfid,
        "CPC_BID_EXECUTED",
        simulation_id,
        details=payload,
        agent_id=agent_id,
        state="EXECUTING",
        causation_id=causation_id or dfid,
    )


def record_monitor_tick(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    state: str,
    details: Dict[str, Any],
    agent_id: Optional[str] = None,
    causation_id: Optional[str] = None,
) -> None:
    sev = "WARNING" if str(state).upper() == "ALERT" else "INFO"
    _record(
        audit,
        dfid,
        "MONITOR_TICK",
        simulation_id,
        details=details,
        agent_id=agent_id,
        state=state,
        severity=sev,
        causation_id=causation_id or dfid,
    )


def record_agent_suspended(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    details: Dict[str, Any],
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid,
        "AGENT_SUSPENDED",
        simulation_id,
        details={
            "agent_id": agent_id,
            "reason": reason,
            **details,
        },
        agent_id=agent_id,
        state="SUSPENDED",
        severity="WARNING",
        causation_id=causation_id or dfid,
    )


def filter_events_by_simulation(
    events: List[Dict[str, Any]],
    simulation_id: str,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for ev in events:
        det = ev.get("details") or {}
        if det.get("simulation_id") == simulation_id:
            out.append(ev)
    return out


def cpc_executions_chronological(
    audit: AuditStore,
    simulation_id: str,
) -> List[Dict[str, Any]]:
    events = audit.all_events_chronological()
    rows: List[Dict[str, Any]] = []
    for ev in events:
        et = ev.get("event") or ev.get("event_type")
        if et != "CPC_BID_EXECUTED":
            continue
        det = ev.get("details") or {}
        if det.get("simulation_id") != simulation_id:
            continue
        rows.append(
            {
                "dfid": ev["dfid"],
                "cpc_bid_usd": float(det["cpc_bid_usd"]),
                "market_cpc_to_win": float(det["market_cpc_to_win"]),
            }
        )
    return rows


def rolling_cpc_stats(
    audit: AuditStore,
    simulation_id: str,
    window: int,
) -> Optional[tuple[float, float]]:
    rows = cpc_executions_chronological(audit, simulation_id)
    if len(rows) < window:
        return None
    sub = rows[-window:]
    avg_bid = sum(r["cpc_bid_usd"] for r in sub) / float(window)
    avg_market = sum(r["market_cpc_to_win"] for r in sub) / float(window)
    return avg_bid, avg_market


def execution_count(audit: AuditStore, simulation_id: str) -> int:
    return len(cpc_executions_chronological(audit, simulation_id))


def rolling_avg_cpc_series(
    audit: AuditStore,
    simulation_id: str,
    window: int,
) -> List[Optional[float]]:
    rows = cpc_executions_chronological(audit, simulation_id)
    series: List[Optional[float]] = []
    for k in range(len(rows)):
        if k + 1 < window:
            series.append(None)
            continue
        lo = k + 1 - window
        sub = rows[lo:k + 1]
        series.append(
            sum(float(r["cpc_bid_usd"]) for r in sub) / float(window)
        )
    return series

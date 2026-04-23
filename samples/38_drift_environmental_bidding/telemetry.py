"""Append-only telemetry via ``StorageBundle.decision_audit`` (no raw SQL)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.storage import StorageBundle


def record_simulation_start(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"simulation_id": simulation_id, **(details or {})}
    bundle.decision_audit.record(simulation_id, "SIMULATION_START", details=payload)


def record_simulation_end(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    status: str,
    stopped_reason: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {
        "simulation_id": simulation_id,
        "status": status,
        "stopped_reason": stopped_reason,
        **(details or {}),
    }
    bundle.decision_audit.record(simulation_id, "SIMULATION_END", details=payload)


def record_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    details: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_COMPILED",
        details={"simulation_id": simulation_id, **details},
    )


def record_policy_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    details: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        state="EMITTED",
        details={"simulation_id": simulation_id, **details},
    )


def record_dim_validation(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    verdict: str,
    reason: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "DIM_VALIDATION",
        state=verdict,
        details={"simulation_id": simulation_id, "reason": reason},
    )


def record_cpc_bid_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    cpc_bid_usd: float,
    market_cpc_to_win: float,
    cycle_id: str,
    idempotency_key: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "cpc_bid_usd": cpc_bid_usd,
        "market_cpc_to_win": market_cpc_to_win,
        "cycle_id": cycle_id,
        "idempotency_key": idempotency_key,
    }
    if extra:
        payload.update(extra)
    bundle.decision_audit.record(dfid, "CPC_BID_EXECUTED", details=payload)


def record_monitor_tick(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    state: str,
    details: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        state=state,
        details={"simulation_id": simulation_id, **details},
    )


def record_agent_suspended(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    details: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AGENT_SUSPENDED",
        state="SUSPENDED",
        details={
            "simulation_id": simulation_id,
            "agent_id": agent_id,
            "reason": reason,
            **details,
        },
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
    bundle: StorageBundle,
    simulation_id: str,
) -> List[Dict[str, Any]]:
    events = bundle.decision_audit.all_events_chronological()
    rows: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("event") != "CPC_BID_EXECUTED":
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
    bundle: StorageBundle,
    simulation_id: str,
    window: int,
) -> Optional[tuple[float, float]]:
    rows = cpc_executions_chronological(bundle, simulation_id)
    if len(rows) < window:
        return None
    sub = rows[-window:]
    avg_bid = sum(r["cpc_bid_usd"] for r in sub) / float(window)
    avg_market = sum(r["market_cpc_to_win"] for r in sub) / float(window)
    return avg_bid, avg_market


def execution_count(bundle: StorageBundle, simulation_id: str) -> int:
    return len(cpc_executions_chronological(bundle, simulation_id))


def rolling_avg_cpc_series(
    bundle: StorageBundle,
    simulation_id: str,
    window: int,
) -> List[Optional[float]]:
    rows = cpc_executions_chronological(bundle, simulation_id)
    series: List[Optional[float]] = []
    for k in range(len(rows)):
        if k + 1 < window:
            series.append(None)
            continue
        lo = k + 1 - window
        sub = rows[lo : k + 1]
        series.append(sum(float(r["cpc_bid_usd"]) for r in sub) / float(window))
    return series

"""Named helpers over ``AuditStore`` / ``decision_audit`` (Sample Guide §9.3–§9.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage import AuditStore


def _with_simulation(simulation_id: str, details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(details or {})
    out.setdefault("simulation_id", simulation_id)
    return out


def _governance_agents(config: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not config:
        return []
    rows: List[Dict[str, Any]] = []
    for a in config.get("agents") or []:
        c = a.get("contract") or {}
        rows.append(
            {
                "agent_id": a.get("agent_id"),
                "owner": a.get("owner"),
                "version": a.get("version"),
                "effective_from": a.get("effective_from"),
                "effective_until": a.get("effective_until"),
                "approved_by": a.get("approved_by"),
                "role": c.get("role"),
            }
        )
    return rows


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    llm_backend: str = "",
    sample: str = "33_insurance_underwriting",
    run_id: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    rid = run_id or simulation_id
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "run_id": rid,
        "sample": sample,
        "topology": "C-DL+PCI",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "agents": _governance_agents(config),
        "seeds": (config or {}).get("simulation", {}).get("seeds", {}),
    }
    if llm_backend:
        details["llm_backend"] = llm_backend
    aid: Optional[str] = None
    agents = (config or {}).get("agents") or []
    if agents:
        aid = str(agents[0].get("agent_id") or "") or None
    audit.record(
        simulation_id,
        "SIMULATION_START",
        details=details,
        agent_id=aid,
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
    elapsed_seconds: Optional[float] = None,
    decisions_total: int = 0,
    executions_total: int = 0,
    agent_id: Optional[str] = None,
) -> None:
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "status": status,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "decisions_total": decisions_total,
        "executions_total": executions_total,
    }
    if error_message:
        details["error_message"] = error_message
    else:
        details["error_message"] = None
    if elapsed_seconds is not None:
        details["elapsed_seconds"] = elapsed_seconds
    audit.record(
        simulation_id,
        "SIMULATION_END",
        details=details,
        agent_id=agent_id,
    )


def record_underwriting_step(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    event: str,
    *,
    step_id: str = "",
    state: str = "",
    details: Optional[Dict[str, Any]] = None,
    agent_id: Optional[str] = None,
) -> None:
    merged = _with_simulation(simulation_id, details)
    if agent_id:
        merged.setdefault("agent_id", agent_id)
    audit.record(
        dfid,
        event,
        step_id=step_id,
        state=state,
        details=merged,
        agent_id=agent_id,
    )

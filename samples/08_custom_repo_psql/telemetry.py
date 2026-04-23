"""Telemetry — ``runtime.audit.record`` wrappers (Sample Guide §9.3)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage.base import AuditStore


def _agents_governance_payload(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for a in config.get("agents", []) or []:
        c = a.get("contract") or {}
        out.append(
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
    return out


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    config: Dict[str, Any],
    *,
    llm_backend: str,
    topology: str = "classic",
) -> None:
    sim = config.get("simulation") or {}
    run_id = str(sim.get("run_id", simulation_id))
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "run_id": run_id,
        "sample": "08_custom_repo_psql",
        "topology": topology,
        "llm_backend": llm_backend,
        "agents": _agents_governance_payload(config),
        "seeds": sim.get("seeds", {}),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    audit.record(simulation_id, "SIMULATION_START", details=details)


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    error_message: Optional[str] = None,
    elapsed_seconds: float = 0.0,
    decisions_total: int = 0,
    executions_total: int = 0,
) -> None:
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "status": status,
        "error_message": error_message,
        "elapsed_seconds": elapsed_seconds,
        "decisions_total": decisions_total,
        "executions_total": executions_total,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    audit.record(simulation_id, "SIMULATION_END", details=details)


def record_agent_decision(
    audit: AuditStore,
    dfid: str,
    *,
    simulation_id: str,
    agent_id: str,
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    explain_narrative: str = "",
) -> None:
    audit.record(
        dfid,
        "AGENT_DECISION",
        details={
            "simulation_id": simulation_id,
            "agent_id": agent_id,
            "policy_kind": policy_kind,
            "verdict": verdict,
            "reason": reason,
            "confidence": confidence,
            "justification": justification,
            "explain_narrative": explain_narrative,
        },
    )

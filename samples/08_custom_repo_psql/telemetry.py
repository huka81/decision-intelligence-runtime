"""Telemetry — ``AuditStore.record`` paired with ``decision_audit_events``.

Wrappers align with ``src/dir_core/storage/schema.sql`` and telemetry
guidelines (``07-telemetry-guidelines.md``):

* ``root_dfid`` = ``simulation_id`` for run lineage; per-flow ``dfid`` is the
  execution id (classic: one DFID per run for ``AGENT_DECISION``).
* ``detail_json`` includes ``correlation_id`` (= ``simulation_id``).
* ``step_id`` / ``state`` / ``severity`` use first-class columns.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage.base import AuditStore


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
    details = _detail_base(
        simulation_id,
        {
            "run_id": run_id,
            "sample": "08_custom_repo_psql",
            "topology": topology,
            "llm_backend": llm_backend,
            "agents": _agents_governance_payload(config),
            "seeds": sim.get("seeds", {}),
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    agents = config.get("agents") or []
    first_id = str(agents[0].get("agent_id", "")) if agents else ""
    agent_kw: Dict[str, Any] = {}
    if first_id:
        agent_kw["agent_id"] = first_id
    audit.record(
        simulation_id,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=details,
        root_dfid=simulation_id,
        severity="INFO",
        **agent_kw,
    )


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
    extra: Dict[str, Any] = {
        "status": status,
        "elapsed_seconds": elapsed_seconds,
        "decisions_total": decisions_total,
        "executions_total": executions_total,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if error_message is not None:
        extra["error_message"] = error_message
    sev = "ERROR" if status.lower() == "error" else "INFO"
    audit.record(
        simulation_id,
        "SIMULATION_END",
        step_id="SIMULATION",
        state=status.upper(),
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity=sev,
    )


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
    v_upper = str(verdict).upper()
    sev = "INFO"
    if v_upper in ("REJECT", "ESCALATE", "SELF_CHECK_FAILED"):
        sev = "WARNING"
    audit.record(
        dfid,
        "AGENT_DECISION",
        step_id="ROA_DIM",
        state=v_upper,
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "policy_kind": policy_kind,
                "verdict": verdict,
                "reason": reason,
                "confidence": confidence,
                "justification": justification,
                "explain_narrative": explain_narrative,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )

"""Append-only audit helpers for sample 06 (``decision_audit_events``)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dir_core.storage.base import AuditStore


def _trace(
    run_id: str,
    details: Dict[str, Any],
    *,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    out = dict(details)
    out.setdefault("run_id", run_id)
    out.setdefault("simulation_id", run_id)
    out.setdefault("correlation_id", run_id)
    if causation_id:
        out.setdefault("causation_id", causation_id)
    return out


def record_demo_start(
    audit: AuditStore,
    run_id: str,
    *,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = _trace(
        run_id,
        {
            "sample": "06_agent_registry",
            "topology": "registry-demo",
            "started_at": datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        },
    )
    audit.record(
        run_id,
        "SIMULATION_START",
        state="CREATED",
        details=payload,
        root_dfid=run_id,
        severity="INFO",
    )


def record_handshake_accepted(
    audit: AuditStore,
    run_id: str,
    dfid: str,
    *,
    agent_id: str,
    priority: int,
    agent_version: str,
) -> None:
    audit.record(
        dfid,
        "AGENT_HANDSHAKE_ACCEPTED",
        state="ACTIVE",
        details=_trace(
            run_id,
            {
                "agent_id": agent_id,
                "priority": priority,
                "agent_version": agent_version,
                "session_issued": True,
            },
            causation_id=dfid,
        ),
        root_dfid=run_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_demo_end(
    audit: AuditStore,
    run_id: str,
    *,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = _trace(
        run_id,
        {
            "status": status,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            **(details or {}),
        },
    )
    sev = "ERROR" if status != "ok" else "INFO"
    st = "COMPLETED" if status == "ok" else "FAILED"
    audit.record(
        run_id,
        "SIMULATION_END",
        state=st,
        details=payload,
        root_dfid=run_id,
        severity=sev,
    )

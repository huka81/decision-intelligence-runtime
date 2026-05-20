"""Append-only audit for sample 04 (``decision_audit_events``)."""

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
    agent_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    payload = _trace(
        run_id,
        {
            "sample": "04_context_store",
            "topology": "context-store-demo",
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
        agent_id=agent_id,
        severity="INFO",
    )


def record_agent_state_updated(
    audit: AuditStore,
    run_id: str,
    *,
    agent_id: str,
    keys_updated: list[str],
    causation_id: Optional[str] = None,
) -> None:
    audit.record(
        run_id,
        "AGENT_STATE_UPDATED",
        state="RUNNING",
        details=_trace(
            run_id,
            {"keys_updated": keys_updated},
            causation_id=causation_id or run_id,
        ),
        root_dfid=run_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_context_session_updated(
    audit: AuditStore,
    run_id: str,
    flow_dfid: str,
    *,
    agent_id: str,
    keys_updated: list[str],
    causation_id: Optional[str] = None,
) -> None:
    audit.record(
        flow_dfid,
        "CONTEXT_SESSION_UPDATED",
        state="RUNNING",
        details=_trace(
            run_id,
            {"flow_dfid": flow_dfid, "keys_updated": keys_updated},
            causation_id=causation_id or flow_dfid,
        ),
        root_dfid=run_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_working_context_compiled(
    audit: AuditStore,
    run_id: str,
    flow_dfid: str,
    *,
    agent_id: str,
    session_keys: int,
    state_keys: int,
    causation_id: Optional[str] = None,
) -> None:
    audit.record(
        flow_dfid,
        "WORKING_CONTEXT_COMPILED",
        state="RUNNING",
        details=_trace(
            run_id,
            {
                "flow_dfid": flow_dfid,
                "session_key_count": session_keys,
                "state_key_count": state_keys,
            },
            causation_id=causation_id or flow_dfid,
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

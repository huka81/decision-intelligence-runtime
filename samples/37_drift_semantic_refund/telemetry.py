"""Map domain steps to ``bundle.decision_audit.record`` / audit table rows.

Aligned with ``src/dir_core/storage/schema.sql`` and telemetry guidelines:

* ``root_dfid`` = ``simulation_id`` (run lineage); per-ticket ``dfid`` = execution id.
* ``detail_json`` includes ``correlation_id`` (= ``simulation_id``).
* ``step_id`` / ``state`` / ``severity`` use first-class columns.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from dir_core.storage import StorageBundle


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


def record_simulation_start(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    details = _detail_base(simulation_id, extra)
    aid = (extra or {}).get("agent_id")
    agent_kw: Dict[str, Any] = {}
    if isinstance(aid, str) and aid:
        agent_kw["agent_id"] = aid
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=details,
        root_dfid=simulation_id,
        severity="INFO",
        **agent_kw,
    )


def record_simulation_end(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    status: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    payload = {"status": status, **(extra or {})}
    sev = "ERROR" if status.lower() == "error" else "INFO"
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_END",
        step_id="SIMULATION",
        state=status.upper(),
        details=_detail_base(simulation_id, payload),
        root_dfid=simulation_id,
        severity=sev,
    )


def record_refund_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    input_ref: str,
    delay_hours: float,
    snapshot_id: str,
    order_ref: str,
    channel: str,
    subject: str,
    message_preview: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_COMPILED",
        step_id="CONTEXT_COMPILED",
        state="READY",
        details=_detail_base(
            simulation_id,
            {
                "input_ref": input_ref,
                "delay_hours": delay_hours,
                "snapshot_id": snapshot_id,
                "order_ref": order_ref,
                "channel": channel,
                "subject": subject,
                "message_preview": message_preview,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_no_refund_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "NO_REFUND_PROPOSAL",
        step_id="NO_REFUND_PROPOSAL",
        state="SKIPPED",
        details=_detail_base(simulation_id, {"reason": reason}),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_policy_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    refund_amount_eur: float,
    policy_kind: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        step_id="POLICY_PROPOSAL",
        state="EMITTED",
        details=_detail_base(
            simulation_id,
            {
                "refund_amount_eur": refund_amount_eur,
                "policy_kind": policy_kind,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_dim_validation(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    verdict: str,
    reason: str,
) -> None:
    v_upper = str(verdict).upper()
    sev = "INFO"
    if v_upper in ("REJECT", "ROA_FAIL", "ESCALATE"):
        sev = "WARNING"
    bundle.decision_audit.record(
        dfid,
        "DIM_VALIDATION",
        step_id="DIM_VALIDATION",
        state=v_upper,
        details=_detail_base(simulation_id, {"reason": reason}),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_refund_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    refund_amount_eur: float,
    delay_hours: float,
    ticket_id: str,
    order_ref: str,
    channel: str,
    policy_kind: str,
    proposal_dump: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "REFUND_EXECUTED",
        step_id="REFUND_EXECUTED",
        state="COMPLETED",
        details=_detail_base(
            simulation_id,
            {
                "refund_amount_eur": refund_amount_eur,
                "delay_hours": delay_hours,
                "ticket_id": ticket_id,
                "order_ref": order_ref,
                "channel": channel,
                "policy_kind": policy_kind,
                "proposal": proposal_dump,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_monitor_tick(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    state: str,
    violation_rate: float,
    window_size: int,
    threshold: float,
    min_delay_hours_for_refund: float,
) -> None:
    st = str(state).upper()
    sev = "WARNING" if st == "ALERT" else "INFO"
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        step_id="MONITOR_TICK",
        state=st,
        details=_detail_base(
            simulation_id,
            {
                "violation_rate": round(violation_rate, 4),
                "window_size": window_size,
                "threshold": threshold,
                "min_delay_hours_for_refund": min_delay_hours_for_refund,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_agent_suspended(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    violation_rate: float,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AGENT_SUSPENDED",
        step_id="AGENT_SUSPENDED",
        state="SUSPENDED",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "reason": reason,
                "violation_rate": round(violation_rate, 4),
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )

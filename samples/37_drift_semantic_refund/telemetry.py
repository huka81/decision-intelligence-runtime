"""Telemetry helpers: map domain steps to ``bundle.decision_audit.record``."""

from __future__ import annotations

from typing import Any, Dict, Optional

from dir_core.storage import StorageBundle


def _details(simulation_id: str, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    d: Dict[str, Any] = {"simulation_id": simulation_id}
    if extra:
        d.update(extra)
    return d


def record_simulation_start(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_START",
        details=_details(simulation_id, extra),
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
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_END",
        details=_details(simulation_id, payload),
    )


def record_refund_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
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
        state="READY",
        details=_details(
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
    )


def record_no_refund_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    reason: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "NO_REFUND_PROPOSAL",
        state="SKIPPED",
        details=_details(simulation_id, {"reason": reason}),
    )


def record_policy_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    refund_amount_eur: float,
    policy_kind: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        state="EMITTED",
        details=_details(
            simulation_id,
            {"refund_amount_eur": refund_amount_eur, "policy_kind": policy_kind},
        ),
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
        details=_details(simulation_id, {"reason": reason}),
    )


def record_refund_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
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
        state="COMPLETED",
        details=_details(
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
    )


def record_monitor_tick(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    state: str,
    violation_rate: float,
    window_size: int,
    threshold: float,
    min_delay_hours_for_refund: float,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        state=state,
        details=_details(
            simulation_id,
            {
                "violation_rate": round(violation_rate, 4),
                "window_size": window_size,
                "threshold": threshold,
                "min_delay_hours_for_refund": min_delay_hours_for_refund,
            },
        ),
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
        state="SUSPENDED",
        details=_details(
            simulation_id,
            {
                "agent_id": agent_id,
                "reason": reason,
                "violation_rate": round(violation_rate, 4),
            },
        ),
    )

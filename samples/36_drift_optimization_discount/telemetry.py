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


def record_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    input_ref: str,
    session_keys: list,
    plan: str = "",
    channel: str = "",
    user_reason: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_COMPILED",
        state="READY",
        details=_details(
            simulation_id,
            {
                "input_ref": input_ref,
                "session_keys": session_keys,
                "plan": plan,
                "channel": channel,
                "user_reason": user_reason,
            },
        ),
    )


def record_policy_proposal(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    discount_offered: float,
    policy_kind: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        state="EMITTED",
        details=_details(
            simulation_id,
            {"discount_offered": discount_offered, "policy_kind": policy_kind},
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


def record_retention_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    discount_offered: float,
    policy_kind: str,
    proposal_dump: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "RETENTION_EXECUTED",
        state="COMPLETED",
        details=_details(
            simulation_id,
            {
                "discount_offered": discount_offered,
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
    moving_avg_discount_pct: float,
    window_size: int,
    threshold_pct: float,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        state=state,
        details=_details(
            simulation_id,
            {
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
                "window_size": window_size,
                "threshold_pct": threshold_pct,
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
    moving_avg_discount_pct: float,
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
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
            },
        ),
    )


def record_agent_decision_summary(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    explain_narrative: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        details=_details(
            simulation_id,
            {
                "agent_id": agent_id,
                "policy_kind": policy_kind,
                "verdict": verdict,
                "reason": str(reason),
                "confidence": confidence,
                "justification": justification,
                "explain_narrative": explain_narrative,
            },
        ),
    )

"""Map domain steps to canonical ``decision_audit`` events."""

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
    bundle.decision_audit.record(
        dfid,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity="INFO",
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


def record_context_compiled(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    scenario_label: str,
    customer_id: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_COMPILED",
        step_id="CONTEXT_COMPILED",
        state="READY",
        details=_detail_base(
            simulation_id,
            {
                "scenario_label": scenario_label,
                "customer_id": customer_id,
            },
        ),
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
    policy_kind: str,
    params: Dict[str, Any],
    retry_attempt: int,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "POLICY_PROPOSAL",
        step_id="POLICY_PROPOSAL",
        state="EMITTED",
        details=_detail_base(
            simulation_id,
            {
                "policy_kind": policy_kind,
                "params": params,
                "retry_attempt": retry_attempt,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_airlock_gate(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    gate: str,
    state: str,
    reason: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AIRLOCK_GATE",
        step_id=gate,
        state=state.upper(),
        details=_detail_base(
            simulation_id,
            {"gate": gate, "reason": reason},
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING" if state.upper() != "PASS" else "INFO",
    )


def record_dim_validation(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    verdict: str,
    reason: str,
    retry_count: int = 0,
) -> None:
    v_upper = str(verdict).upper()
    sev = "WARNING" if v_upper in ("REJECT", "ESCALATE") else "INFO"
    bundle.decision_audit.record(
        dfid,
        "DIM_VALIDATION",
        step_id="DIM_VALIDATION",
        state=v_upper,
        details=_detail_base(
            simulation_id,
            {"reason": reason, "retry_count": retry_count},
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )


def record_retention_executed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    discount_pct: float,
    proposal_dump: Dict[str, Any],
) -> None:
    bundle.decision_audit.record(
        dfid,
        "RETENTION_EXECUTED",
        step_id="RETENTION_EXECUTED",
        state="COMPLETED",
        details=_detail_base(
            simulation_id,
            {
                "discount_offered": discount_pct,
                "policy_kind": policy_kind,
                "proposal": proposal_dump,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_escalation_requested(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "ESCALATION_REQUESTED",
        step_id="ESCALATION",
        state="GRANTED",
        details=_detail_base(simulation_id, {"reason": reason}),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )


def record_monitor_tick(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    state: str,
    moving_avg_discount_pct: float,
    window_size: int,
    threshold_pct: float,
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
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
                "window_size": window_size,
                "threshold_pct": threshold_pct,
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
    moving_avg_discount_pct: float,
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
                "moving_avg_discount_pct": round(moving_avg_discount_pct, 4),
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )


def record_context_tax(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    retry_attempt: int,
    estimated_tokens: int,
    prior_failure_trace: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CONTEXT_TAX",
        step_id="CONTEXT_TAX",
        state=f"RETRY_{retry_attempt + 1}",
        details=_detail_base(
            simulation_id,
            {
                "retry_attempt": retry_attempt,
                "retry_number": retry_attempt + 1,
                "estimated_input_tokens": estimated_tokens,
                "prior_failure_trace": prior_failure_trace,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING" if retry_attempt > 0 else "INFO",
    )


def record_agent_decision_summary(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    scenario_label: str,
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    explain_narrative: str,
    airlock_trace: Dict[str, str],
    reconstructed_narrative: str = "",
    keyword_overlap: float = 0.0,
) -> None:
    v_upper = str(verdict).upper()
    sev = "WARNING" if v_upper in ("REJECT", "ESCALATE") else "INFO"
    payload: Dict[str, Any] = {
        "scenario_label": scenario_label,
        "agent_id": agent_id,
        "policy_kind": policy_kind,
        "verdict": verdict,
        "reason": str(reason),
        "confidence": confidence,
        "justification": justification,
        "explain_narrative": explain_narrative,
        "airlock_trace": airlock_trace,
    }
    if reconstructed_narrative:
        payload["reconstructed_narrative"] = reconstructed_narrative
    if keyword_overlap > 0.0:
        payload["keyword_overlap"] = round(keyword_overlap, 4)
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        step_id="ROA_DIM",
        state=v_upper,
        details=_detail_base(simulation_id, payload),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity=sev,
    )

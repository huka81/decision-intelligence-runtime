"""Telemetry helpers — canonical decision_audit events."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.storage import AuditStore, StorageBundle


def _detail_base(
    simulation_id: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "correlation_id": simulation_id,
    }
    if extra:
        out.update(extra)
    return out


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    llm_backend: str = "",
    agents: Optional[list] = None,
    seeds: Optional[Dict[str, Any]] = None,
) -> None:
    extra: Dict[str, Any] = {
        "sample": "39_fintech_evidence_governance",
        "topology": "C-DL+PCI",
    }
    if llm_backend:
        extra["llm_backend"] = llm_backend
    if agents:
        extra["agents"] = agents
    if seeds:
        extra["seeds"] = seeds
    audit.record(
        simulation_id,
        "SIMULATION_START",
        step_id="SIMULATION",
        state="RUNNING",
        details=_detail_base(simulation_id, extra),
        root_dfid=simulation_id,
        severity="INFO",
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    decisions_total: int = 0,
    executions_total: int = 0,
    error_message: Optional[str] = None,
    elapsed_seconds: float = 0.0,
) -> None:
    extra: Dict[str, Any] = {
        "status": status,
        "decisions_total": decisions_total,
        "executions_total": executions_total,
        "elapsed_seconds": elapsed_seconds,
    }
    if error_message:
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


def record_evidence_abort(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    scenario_label: str,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "EVIDENCE_ABORT",
        step_id="EVIDENCE",
        state="ABORT",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "scenario_label": scenario_label,
                "reason": reason,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="ERROR",
    )


def record_semantic_alignment_flag(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    flag: str,
    reason: str,
    scenario_label: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "SEMANTIC_ALIGNMENT_FLAG",
        step_id="ALIGNMENT",
        state=flag,
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "flag": flag,
                "reason": reason,
                "scenario_label": scenario_label,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING",
    )


def record_semantic_alignment_abort(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    scenario_label: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "SEMANTIC_ALIGNMENT_ABORT",
        step_id="ALIGNMENT",
        state="ABORT",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "reason": reason,
                "scenario_label": scenario_label,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="ERROR",
    )


def record_pci_verification(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    proof_ok: bool,
    reason: str,
    scenario_label: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "PCI_VERIFICATION",
        step_id="PCI",
        state="OK" if proof_ok else "REJECT",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "proof_ok": proof_ok,
                "reason": reason,
                "scenario_label": scenario_label,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO" if proof_ok else "ERROR",
    )


def record_credit_decision(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    verdict: str,
    reason: str,
    scenario_label: str = "",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CREDIT_DECISION",
        step_id="DIM",
        state=verdict,
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "verdict": verdict,
                "reason": str(reason),
                "scenario_label": scenario_label,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="INFO",
    )


def record_credit_limit_raised(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    customer_id: str,
    new_limit_pln: float,
    high_risk: bool,
    declared_income_pln: float | None = None,
    idempotency_key_prefix: str = "",
    scenario_label: str = "",
) -> None:
    payload: Dict[str, Any] = {
        "agent_id": agent_id,
        "customer_id": customer_id,
        "new_limit_pln": new_limit_pln,
        "high_risk": high_risk,
        "idempotency_key_prefix": idempotency_key_prefix,
        "scenario_label": scenario_label,
    }
    if declared_income_pln is not None:
        payload["declared_income_pln"] = declared_income_pln
    bundle.decision_audit.record(
        dfid,
        "CREDIT_LIMIT_RAISED",
        step_id="EXECUTE",
        state="OK",
        details=_detail_base(
            simulation_id,
            payload,
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
    high_risk_rate: float,
    window_size: int,
    threshold: float,
    phase: str = "drift_batch",
    high_risk_count: int | None = None,
    window_high_risk_flags: List[bool] | None = None,
    window_labels: List[str] | None = None,
    drift_executions_total: int | None = None,
) -> None:
    payload: Dict[str, Any] = {
        "agent_id": agent_id,
        "high_risk_approval_rate": high_risk_rate,
        "window_size": window_size,
        "threshold": threshold,
        "phase": phase,
    }
    if high_risk_count is not None:
        payload["high_risk_count"] = high_risk_count
    if window_high_risk_flags is not None:
        payload["window_high_risk_flags"] = window_high_risk_flags
    if window_labels is not None:
        payload["window_labels"] = window_labels
    if drift_executions_total is not None:
        payload["drift_executions_total"] = drift_executions_total
    bundle.decision_audit.record(
        dfid,
        "MONITOR_TICK",
        step_id="MONITOR",
        state=state,
        details=_detail_base(
            simulation_id,
            payload,
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="WARNING" if state == "ALERT" else "INFO",
    )


def record_agent_suspended(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    high_risk_rate: float,
    phase: str = "drift_batch",
) -> None:
    bundle.decision_audit.record(
        dfid,
        "AGENT_SUSPENDED",
        step_id="MONITOR",
        state="SUSPENDED",
        details=_detail_base(
            simulation_id,
            {
                "agent_id": agent_id,
                "reason": reason,
                "high_risk_approval_rate": high_risk_rate,
                "phase": phase,
            },
        ),
        root_dfid=simulation_id,
        agent_id=agent_id,
        severity="ERROR",
    )

"""Named helpers over ``AuditStore`` / ``decision_audit_events`` (§9.3–§9.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from dir_core.storage.base import AuditStore


def _with_trace(
    simulation_id: str,
    details: Optional[Dict[str, Any]],
    *,
    causation_id: Optional[str] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(details or {})
    out.setdefault("simulation_id", simulation_id)
    out.setdefault("correlation_id", simulation_id)
    if causation_id:
        out.setdefault("causation_id", causation_id)
    return out


def _record(
    audit: AuditStore,
    dfid: str,
    event: str,
    simulation_id: str,
    *,
    details: Optional[Dict[str, Any]] = None,
    root_dfid: Optional[str] = None,
    agent_id: Optional[str] = None,
    step_id: str = "",
    state: str = "",
    severity: str = "INFO",
    causation_id: Optional[str] = None,
) -> None:
    merged = _with_trace(simulation_id, details, causation_id=causation_id)
    audit.record(
        dfid,
        event,
        step_id=step_id,
        state=state,
        details=merged,
        root_dfid=root_dfid or simulation_id,
        agent_id=agent_id,
        severity=severity,
    )


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    llm_backend: str = "",
    sample: str = "35_crewai_roa_wrapper",
    topology: str = "classic",
) -> None:
    details: Dict[str, Any] = {
        "sample": sample,
        "topology": topology,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    if llm_backend:
        details["llm_backend"] = llm_backend
    _record(
        audit,
        simulation_id,
        "SIMULATION_START",
        simulation_id,
        details=details,
        root_dfid=simulation_id,
        state="CREATED",
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
    elapsed_seconds: Optional[float] = None,
    scenarios_total: int = 0,
) -> None:
    details: Dict[str, Any] = {"status": status}
    if error_message:
        details["error_message"] = error_message
    else:
        details["error_message"] = None
    details["finished_at"] = datetime.now(timezone.utc).isoformat()
    if elapsed_seconds is not None:
        details["elapsed_seconds"] = float(elapsed_seconds)
    if scenarios_total:
        details["scenarios_total"] = scenarios_total
    sev = "ERROR" if status not in ("ok", "completed") else "INFO"
    end_state = "COMPLETED" if status in ("ok", "completed") else "FAILED"
    _record(
        audit,
        simulation_id,
        "SIMULATION_END",
        simulation_id,
        details=details,
        root_dfid=simulation_id,
        state=end_state,
        severity=sev,
    )


def record_agent_decision(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    scenario_label: str = "",
    executed: bool = False,
    order_id: str = "",
    explain_narrative: str = "",
    self_check_passed: bool = True,
    self_check_reason: str = "",
    contract_role: str = "",
    contract_allowed_policy_types: Optional[List[str]] = None,
    amount_eur: float = 0.0,
    causation_id: Optional[str] = None,
) -> None:
    details: Dict[str, Any] = {
        "agent_id": agent_id,
        "policy_kind": policy_kind,
        "verdict": verdict,
        "reason": reason,
        "confidence": confidence,
        "justification": justification,
        "scenario_label": scenario_label,
        "executed": executed,
        "order_id": order_id,
        "amount_eur": float(amount_eur),
        "self_check_passed": self_check_passed,
        "self_check_reason": self_check_reason,
        "contract_role": contract_role,
    }
    if contract_allowed_policy_types is not None:
        details["contract_allowed_policy_types"] = (
            contract_allowed_policy_types
        )
    if explain_narrative:
        details["explain_narrative"] = explain_narrative
    sev = "WARNING" if str(verdict).upper() == "ESCALATE" else "INFO"
    _record(
        audit,
        dfid,
        "AGENT_DECISION",
        simulation_id,
        details=details,
        agent_id=agent_id,
        state=str(verdict),
        severity=sev,
        causation_id=causation_id or dfid,
    )


def record_claims_self_check_failed(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    scenario_label: str = "",
    explain_narrative: str = "",
    causation_id: Optional[str] = None,
) -> None:
    det: Dict[str, Any] = {
        "agent_id": agent_id,
        "reason": reason,
        "scenario_label": scenario_label,
    }
    if explain_narrative:
        det["explain_narrative"] = explain_narrative
    _record(
        audit,
        dfid,
        "CLAIMS_SELF_CHECK_FAILED",
        simulation_id,
        details=det,
        agent_id=agent_id,
        state="ABORTED",
        severity="WARNING",
        causation_id=causation_id or dfid,
    )


def record_claims_refund_execution(
    audit: AuditStore,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    order_id: str,
    idempotency_key_value: str,
    amount_eur: float,
    causation_id: Optional[str] = None,
) -> None:
    _record(
        audit,
        dfid,
        "CLAIM_REFUND_EXECUTED",
        simulation_id,
        details={
            "agent_id": agent_id,
            "policy_kind": policy_kind,
            "order_id": order_id,
            "idempotency_key": idempotency_key_value,
            "amount_eur": amount_eur,
            "mode": "dry_run",
        },
        agent_id=agent_id,
        state="EXECUTING",
        causation_id=causation_id or dfid,
    )

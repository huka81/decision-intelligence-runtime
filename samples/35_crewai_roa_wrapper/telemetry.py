"""Named helpers over ``bundle.decision_audit`` (Sample Guide §9.3–§9.4)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.storage import StorageBundle


def _with_simulation(simulation_id: str, details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict(details or {})
    out.setdefault("simulation_id", simulation_id)
    return out


def record_simulation_start(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    llm_backend: str = "",
    sample: str = "35_crewai_roa_wrapper",
) -> None:
    details: Dict[str, Any] = {"simulation_id": simulation_id, "sample": sample}
    if llm_backend:
        details["llm_backend"] = llm_backend
    bundle.decision_audit.record(simulation_id, "SIMULATION_START", details=details)


def record_simulation_end(
    bundle: StorageBundle,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
) -> None:
    details: Dict[str, Any] = {"simulation_id": simulation_id, "status": status}
    if error_message:
        details["error_message"] = error_message
    bundle.decision_audit.record(simulation_id, "SIMULATION_END", details=details)


def record_agent_decision(
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
    scenario_label: str = "",
    executed: bool = False,
    order_id: str = "",
    explain_narrative: str = "",
    self_check_passed: bool = True,
    self_check_reason: str = "",
    contract_role: str = "",
    contract_allowed_policy_types: Optional[List[str]] = None,
    amount_eur: float = 0.0,
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
        details["contract_allowed_policy_types"] = contract_allowed_policy_types
    if explain_narrative:
        details["explain_narrative"] = explain_narrative
    bundle.decision_audit.record(
        dfid,
        "AGENT_DECISION",
        details=_with_simulation(simulation_id, details),
    )


def record_claims_self_check_failed(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    reason: str,
    scenario_label: str = "",
    explain_narrative: str = "",
) -> None:
    det: Dict[str, Any] = {
        "agent_id": agent_id,
        "reason": reason,
        "scenario_label": scenario_label,
    }
    if explain_narrative:
        det["explain_narrative"] = explain_narrative
    bundle.decision_audit.record(
        dfid,
        "CLAIMS_SELF_CHECK_FAILED",
        details=_with_simulation(simulation_id, det),
    )


def record_claims_refund_execution(
    bundle: StorageBundle,
    dfid: str,
    simulation_id: str,
    *,
    agent_id: str,
    policy_kind: str,
    order_id: str,
    idempotency_key_value: str,
    amount_eur: float,
) -> None:
    bundle.decision_audit.record(
        dfid,
        "CLAIM_REFUND_EXECUTED",
        details=_with_simulation(
            simulation_id,
            {
                "agent_id": agent_id,
                "policy_kind": policy_kind,
                "order_id": order_id,
                "idempotency_key": idempotency_key_value,
                "amount_eur": amount_eur,
                "mode": "dry_run",
            },
        ),
    )

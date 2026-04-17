"""Telemetry helpers — named ``bundle.decision_audit.record`` wrappers (Sample Guide §9.3)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from dir_core.storage import AuditStore
from dir_core.utils.logging_utils import log_with_dfid

logger = logging.getLogger(__name__)


def record_simulation_start(
    audit: AuditStore,
    simulation_id: str,
    *,
    llm_backend: str = "",
) -> None:
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "sample": "32_fraud_gate",
    }
    if llm_backend:
        details["llm_backend"] = llm_backend
    audit.record(
        simulation_id,
        "SIMULATION_START",
        details=details,
    )


def record_simulation_end(
    audit: AuditStore,
    simulation_id: str,
    *,
    status: str,
    error_message: str = "",
) -> None:
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "status": status,
    }
    if error_message:
        details["error_message"] = error_message
    audit.record(simulation_id, "SIMULATION_END", details=details)


def record_agent_decision(
    audit: AuditStore,
    dfid: str,
    *,
    simulation_id: str,
    agent_id: str,
    scenario_label: str,
    tx_id: str = "",
    policy_kind: str,
    verdict: str,
    reason: str,
    confidence: float,
    justification: str,
    amount: float = 0.0,
    user_id: str = "",
    geo_country: str = "",
    device_id: str = "",
    velocity_24h: int = 0,
    contract_role: str = "",
    contract_allowed_policy_types: Optional[List[str]] = None,
    explain_narrative: str = "",
    explain_signals: Optional[List[str]] = None,
    explain_risks: Optional[List[str]] = None,
    explain_opportunities: Optional[List[str]] = None,
    policy_proposed_action: str = "",
    policy_reason_code: str = "",
    policy_risk_score: float = 0.0,
    policy_stage_confidence: float = -1.0,
    self_check_passed: bool = True,
    self_check_reason: str = "",
    drift_attack: bool = False,
) -> None:
    allowed = contract_allowed_policy_types or []
    details: Dict[str, Any] = {
        "simulation_id": simulation_id,
        "agent_id": agent_id,
        "scenario_label": scenario_label,
        "tx_id": tx_id,
        "policy_kind": policy_kind,
        "verdict": verdict,
        "reason": str(reason),
        "confidence": confidence,
        "justification": justification,
        "amount": amount,
        "user_id": user_id,
        "geo_country": geo_country,
        "device_id": device_id,
        "velocity_24h": velocity_24h,
        "contract_role": contract_role,
        "contract_allowed_policy_types": allowed,
        "explain_narrative": explain_narrative,
        "explain_signals": list(explain_signals or []),
        "explain_risks": list(explain_risks or []),
        "explain_opportunities": list(explain_opportunities or []),
        "policy_proposed_action": policy_proposed_action or policy_kind,
        "policy_reason_code": policy_reason_code,
        "policy_risk_score": policy_risk_score,
        "policy_stage_confidence": (
            policy_stage_confidence
            if policy_stage_confidence >= 0.0
            else confidence
        ),
        "self_check_passed": self_check_passed,
        "self_check_reason": self_check_reason,
        "drift_attack": drift_attack,
    }
    audit.record(
        dfid,
        "AGENT_DECISION",
        details=details,
    )


def record_payment_executed(
    audit: AuditStore,
    dfid: str,
    *,
    simulation_id: str,
    tx_id: str,
    user_id: str,
    amount: float,
    idempotency_key_prefix: str,
    cached: bool,
) -> None:
    audit.record(
        dfid,
        "PAYMENT_GATEWAY_ALLOW",
        details={
            "simulation_id": simulation_id,
            "tx_id": tx_id,
            "user_id": user_id,
            "amount": amount,
            "idempotency_key_prefix": idempotency_key_prefix,
            "cached": cached,
        },
    )
    log_with_dfid(
        logger,
        dfid,
        logging.INFO,
        "PaymentGateway (mock): ALLOW tx_id=%s user=%s amount=%s cached=%s",
        tx_id,
        user_id,
        amount,
        cached,
    )

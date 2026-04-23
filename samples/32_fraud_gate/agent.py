"""
Fraud ROA agent: Explain -> Policy -> Self-Check -> PolicyProposal.

LLM runs only in User Space.
Kernel gates execution via DIM plus custom JIT validators.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dir_core import PolicyProposal, ResponsibilityContract
from dir_core.utils.llm_client import LLMClient

try:
    from .schemas import FallbackRules, TransactionContext
except ImportError:
    from schemas import FallbackRules, TransactionContext

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        text = m.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _fallback_policy_dict(
    ctx: TransactionContext,
    snapshot_status: Optional[str],
    rules: FallbackRules,
) -> Dict[str, Any]:
    geo_lower = ctx.geo_country.lower()
    high_geo = (
        ctx.amount > rules.block_amount_threshold
        and geo_lower in rules.block_high_risk_countries
    )
    if high_geo:
        return {
            "proposed_action": "BLOCK",
            "justification": (
                "Deterministic fallback: high amount in high-risk geography."
            ),
            "confidence": 0.99,
            "reason_code": "HIGH_RISK_GEO_AMOUNT",
            "risk_score": 0.99,
        }
    if (
        ctx.amount < rules.allow_amount_max
        and ctx.device_id.startswith(rules.allow_device_prefix)
        and ctx.velocity_24h < rules.allow_velocity_max
    ):
        return {
            "proposed_action": "ALLOW",
            "justification": (
                "Deterministic fallback: low amount, known device, low velocity."
            ),
            "confidence": 0.9,
            "reason_code": "LOW_RISK_LEGIT",
            "risk_score": 0.1,
        }
    if snapshot_status == "clean" and ctx.amount < rules.allow_amount_max:
        return {
            "proposed_action": "ALLOW",
            "justification": (
                "Deterministic fallback: clean snapshot and small amount."
            ),
            "confidence": 0.85,
            "reason_code": "LOW_RISK_SNAPSHOT",
            "risk_score": 0.15,
        }
    return {
        "proposed_action": "CHALLENGE",
        "justification": "Deterministic fallback: uncertain case.",
        "confidence": 0.5,
        "reason_code": "UNCERTAIN",
        "risk_score": 0.5,
    }


@dataclass
class FraudRoaResult:
    """ROA stages for audit and HTML report (orchestrator persists via telemetry)."""

    proposal: Optional[PolicyProposal]
    explain_narrative: str
    explain_signals: List[str]
    explain_risks: List[str]
    explain_opportunities: List[str]
    policy_proposed_action: str
    policy_justification: str
    policy_confidence: float
    policy_reason_code: str
    policy_risk_score: float
    self_check_passed: bool
    self_check_reason: str


def _snapshot_id(ctx: TransactionContext, snapshot_status: Optional[str]) -> str:
    payload = json.dumps(
        {
            "user_id": ctx.user_id,
            "amount": ctx.amount,
            "snapshot_status": snapshot_status or "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _as_str_list(val: Any) -> List[str]:
    if not isinstance(val, list):
        return []
    out: List[str] = []
    for x in val:
        out.append(str(x))
    return out


def run_fraud_roa_cycle(
    llm: LLMClient,
    contract: ResponsibilityContract,
    ctx: TransactionContext,
    snapshot_status: Optional[str],
    dfid: str,
    agent_id: str,
    rules: FallbackRules,
) -> FraudRoaResult:
    mission = contract.mission or "You are a fraud analyst for a payment gateway."

    explain_prompt = (
        "ROA_EXPLAIN\n"
        f"user_id={ctx.user_id}\n"
        f"amount={ctx.amount}\n"
        f"geo_country={ctx.geo_country}\n"
        f"device_id={ctx.device_id}\n"
        f"velocity_24h={ctx.velocity_24h}\n"
        f"snapshot_user_status={snapshot_status or 'unknown'}\n\n"
        "Return ONLY JSON with keys: narrative (string), identified_signals (array of strings), "
        "risks (array of strings), opportunities (array of strings)."
    )
    explain_raw = llm.generate(explain_prompt, system=mission)
    ex = parse_llm_json(explain_raw) or {}
    narrative = str(
        ex.get("narrative", "Explain stage produced no structured narrative.")
    )
    signals = _as_str_list(ex.get("identified_signals"))
    risks_ex = _as_str_list(ex.get("risks"))
    opps_ex = _as_str_list(ex.get("opportunities"))

    policy_prompt = (
        "ROA_POLICY\n"
        f"user_id={ctx.user_id}\n"
        f"amount={ctx.amount}\n"
        f"geo_country={ctx.geo_country}\n"
        f"device_id={ctx.device_id}\n"
        f"velocity_24h={ctx.velocity_24h}\n"
        f"snapshot_user_status={snapshot_status or 'unknown'}\n"
        f"narrative={narrative}\n"
        f"identified_signals={json.dumps(signals)}\n\n"
        "Return ONLY JSON: proposed_action ALLOW|BLOCK|CHALLENGE, "
        "justification string, confidence 0-1, reason_code string, risk_score 0-1."
    )
    policy_raw = llm.generate(policy_prompt, system=mission)
    pol = parse_llm_json(policy_raw)
    if pol is None:
        pol = _fallback_policy_dict(ctx, snapshot_status, rules)
        logger.warning("Policy stage not parseable; using deterministic fallback.")
    else:
        proposed = str(pol.get("proposed_action", "")).upper().strip()
        if proposed not in ("ALLOW", "BLOCK", "CHALLENGE"):
            legacy = str(pol.get("action", "")).upper().strip()
            if legacy in ("ALLOW", "BLOCK", "CHALLENGE"):
                pol["proposed_action"] = legacy
            else:
                pol = _fallback_policy_dict(ctx, snapshot_status, rules)
                logger.warning(
                    "Policy stage invalid action; using deterministic fallback."
                )

    proposed_action = str(pol.get("proposed_action", "CHALLENGE")).upper().strip()
    try:
        confidence = float(pol.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    try:
        risk_score = float(pol.get("risk_score", confidence))
    except (TypeError, ValueError):
        risk_score = confidence
    risk_score = max(0.0, min(1.0, risk_score))
    justification = str(pol.get("justification", "")).strip() or "No justification provided."
    reason_code = str(pol.get("reason_code", "UNKNOWN"))

    allowed = list(contract.allowed_policy_types or [])
    if proposed_action not in allowed:
        logger.warning(
            "Self-check failed: proposed_action %s not in %s",
            proposed_action,
            allowed,
        )
        return FraudRoaResult(
            proposal=None,
            explain_narrative=narrative,
            explain_signals=signals,
            explain_risks=risks_ex,
            explain_opportunities=opps_ex,
            policy_proposed_action=proposed_action,
            policy_justification=justification,
            policy_confidence=confidence,
            policy_reason_code=reason_code,
            policy_risk_score=risk_score,
            self_check_passed=False,
            self_check_reason=(
                f"proposed_action {proposed_action} not in allowed_policy_types {allowed}"
            ),
        )
    if confidence < float(contract.escalate_on_uncertainty):
        logger.warning(
            "Self-check failed: confidence %s below escalate_on_uncertainty %s",
            confidence,
            contract.escalate_on_uncertainty,
        )
        return FraudRoaResult(
            proposal=None,
            explain_narrative=narrative,
            explain_signals=signals,
            explain_risks=risks_ex,
            explain_opportunities=opps_ex,
            policy_proposed_action=proposed_action,
            policy_justification=justification,
            policy_confidence=confidence,
            policy_reason_code=reason_code,
            policy_risk_score=risk_score,
            self_check_passed=False,
            self_check_reason=(
                f"confidence {confidence} below escalate_on_uncertainty "
                f"{contract.escalate_on_uncertainty}"
            ),
        )

    snapshot_id = _snapshot_id(ctx, snapshot_status)
    prop = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind=proposed_action,
        params={
            "user_id": ctx.user_id,
            "amount": ctx.amount,
            "geo_country": ctx.geo_country,
            "device_id": ctx.device_id,
            "velocity_24h": ctx.velocity_24h,
            "reason_code": reason_code,
            "risk_score": risk_score,
            "snapshot_id": snapshot_id,
        },
        confidence=confidence,
        justification=justification,
        explain_ref="explain_inline",
    )
    return FraudRoaResult(
        proposal=prop,
        explain_narrative=narrative,
        explain_signals=signals,
        explain_risks=risks_ex,
        explain_opportunities=opps_ex,
        policy_proposed_action=proposed_action,
        policy_justification=justification,
        policy_confidence=confidence,
        policy_reason_code=reason_code,
        policy_risk_score=risk_score,
        self_check_passed=True,
        self_check_reason="",
    )

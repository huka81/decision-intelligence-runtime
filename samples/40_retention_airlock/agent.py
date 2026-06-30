"""User Space ROA agent: Explain -> Policy -> Self-Check -> Proposal."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from dir_core import PolicyProposal
from dir_core.models import ResponsibilityContract
from dir_core.utils.llm_client import LLMClient


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


def run_retention_roa_cycle(
    llm: LLMClient,
    contract: ResponsibilityContract,
    *,
    dfid: str,
    agent_id: str,
    scenario_label: str,
    customer_id: str,
    customer_tier: str,
    email_body: str,
    mock_policy_kind: str,
    mock_discount_pct: float,
    retry_attempt: int = 0,
    prior_failure_trace: str = "",
) -> Tuple[Optional[PolicyProposal], str, str, str]:
    """Returns (proposal_or_none, explain_narrative, justification, fail_reason)."""
    mission = contract.mission or "Retain subscribers with policy-compliant actions."
    common = (
        f"PHASE=explain\nDFID={dfid}\nSCENARIO_LABEL={scenario_label}\n"
        f"CUSTOMER_ID={customer_id}\nTIER={customer_tier}\n"
        f"RETRY_ATTEMPT={retry_attempt}\n"
        f"MOCK_POLICY_KIND={mock_policy_kind}\nMOCK_DISCOUNT_PCT={mock_discount_pct:.4f}\n"
        f"EMAIL_BODY={email_body[:1200]}"
    )
    if prior_failure_trace:
        common += f"\nPRIOR_FAILURE_TRACE={prior_failure_trace[:4000]}"
    explain_raw = llm.generate(common, system=mission)
    ex_obj = parse_llm_json(explain_raw) or {}
    narrative = str(ex_obj.get("narrative") or explain_raw.strip()[:800])

    policy_prompt = common.replace("PHASE=explain", "PHASE=policy", 1)
    policy_raw = llm.generate(policy_prompt, system=mission)
    pol = parse_llm_json(policy_raw)
    if not pol:
        return None, narrative, "", "policy_json_parse_failed"

    policy_kind = str(pol.get("policy_kind") or "")
    params = pol.get("params") if isinstance(pol.get("params"), dict) else {}
    try:
        confidence = float(pol.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    justification = str(pol.get("justification") or "")

    allowed = list(contract.allowed_policy_types or [])
    if policy_kind not in allowed:
        return None, narrative, justification, "self_check_policy_kind"
    if confidence < float(contract.escalate_on_uncertainty):
        return None, narrative, justification, "self_check_confidence"

    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind=policy_kind,
        params=dict(params),
        confidence=confidence,
        justification=justification,
    )
    return proposal, narrative, justification, ""

"""
Simulated ROA path (no LLM): Explain (deterministic narrative) → Policy → Self-Check → Proposal.

Execution remains orchestrator-gated after DIM ``ACCEPT``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from dir_core import PolicyProposal
from dir_core.models import ResponsibilityContract


def run_bidding_roa_cycle(
    *,
    dfid: str,
    agent_id: str,
    contract: ResponsibilityContract,
    market_cpc_to_win: float,
    bid_usd: float,
    cycle_index: int,
    total_cycles: int,
    snapshot_id: str,
) -> Tuple[Optional[PolicyProposal], Dict[str, Any]]:
    """
    Returns ``(proposal or None, roa_audit)`` where ``roa_audit`` holds explain / self-check fields
    for telemetry and HTML reconstruction.
    """
    explain_narrative = (
        f"Cycle {cycle_index + 1}/{total_cycles}: market floor to win placement is "
        f"{market_cpc_to_win:.3f} USD; mission is to stay competitive without breaching the cap."
    )
    proposed_action = "cpc_bid"
    confidence = 0.94

    roa_audit: Dict[str, Any] = {
        "explain_narrative": explain_narrative,
        "proposed_action": proposed_action,
        "self_check_passed": False,
        "self_check_reason": "",
    }

    if proposed_action not in contract.allowed_policy_types:
        roa_audit["self_check_reason"] = "policy not in allowed_policy_types"
        return None, roa_audit
    if confidence < contract.escalate_on_uncertainty:
        roa_audit["self_check_reason"] = "confidence below escalate_on_uncertainty"
        return None, roa_audit

    roa_audit["self_check_passed"] = True
    proposal = PolicyProposal(
        dfid=dfid,
        agent_id=agent_id,
        policy_kind="cpc_bid",
        params={"cpc_bid_usd": bid_usd},
        context_ref=snapshot_id,
        confidence=confidence,
        justification=(
            f"Simulated bid (cycle {cycle_index + 1}/{total_cycles}): stay just above market "
            "to hold top 3."
        ),
    )
    return proposal, roa_audit

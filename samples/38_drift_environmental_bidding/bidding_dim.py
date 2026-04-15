"""
Kernel Space: DIM wrapper for CPC bids (DIR generic gates + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from dir_core.data_types import DimReasonCode, ValidationResult, ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal


def validate_cpc_bid_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    max_cpc_usd: float,
) -> ValidationResult:
    """
    Gate stack: dir.dim.validate_proposal, then deterministic contract check on cpc_bid_usd.
    DIM does not enforce LTV or ROI — only the CPC ceiling.
    """
    verdict, reason = validate_proposal(proposal, context, allowed_agents)
    if verdict == ValidationVerdict.REJECT:
        return verdict, reason

    raw = proposal.params.get("cpc_bid_usd")
    if raw is None:
        return ValidationVerdict.REJECT, "Missing cpc_bid_usd in params"
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return ValidationVerdict.REJECT, "Invalid cpc_bid_usd type"

    if amount <= 0:
        return ValidationVerdict.REJECT, "Non-positive cpc_bid_usd"
    if amount > max_cpc_usd + 1e-9:
        return ValidationVerdict.REJECT, f"CPC_EXCEEDS_CONTRACT max={max_cpc_usd}"

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED


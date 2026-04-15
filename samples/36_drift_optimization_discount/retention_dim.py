"""
Kernel Space: DIM wrapper for retention discounts (DIR generic gates + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from dir_core.data_types import DimReasonCode, ValidationResult, ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal


def validate_retention_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    max_discount_pct: float,
) -> ValidationResult:
    """
    Gate stack: dir.dim.validate_proposal (schema, TTL, RBAC, sample context state),
    then deterministic contract check on discount_offered.
    """
    verdict, reason = validate_proposal(proposal, context, allowed_agents)
    if verdict == ValidationVerdict.REJECT:
        return verdict, reason

    raw = proposal.params.get("discount_offered")
    if raw is None:
        return ValidationVerdict.REJECT, "Missing discount_offered in params"
    try:
        discount = float(raw)
    except (TypeError, ValueError):
        return ValidationVerdict.REJECT, "Invalid discount_offered type"

    if discount < 0:
        return ValidationVerdict.REJECT, "Negative discount_offered"
    if discount > max_discount_pct + 1e-9:
        return ValidationVerdict.REJECT, f"DISCOUNT_EXCEEDS_CONTRACT max={max_discount_pct}"

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED


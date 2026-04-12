"""
Kernel Space: DIM wrapper for retention discounts (DIR generic gates + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal

ValidationVerdict = Literal["ACCEPT", "REJECT"]
ValidationResult = Tuple[ValidationVerdict, str]


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
    if verdict == "REJECT":
        return verdict, reason

    raw = proposal.params.get("discount_offered")
    if raw is None:
        return "REJECT", "Missing discount_offered in params"
    try:
        discount = float(raw)
    except (TypeError, ValueError):
        return "REJECT", "Invalid discount_offered type"

    if discount < 0:
        return "REJECT", "Negative discount_offered"
    if discount > max_discount_pct + 1e-9:
        return "REJECT", f"DISCOUNT_EXCEEDS_CONTRACT max={max_discount_pct}"

    return "ACCEPT", "Validation passed"


"""
Kernel Space: DIM wrapper for retention discounts (generic validate_proposal + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.data_types import DimReasonCode, ValidationResult, ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal


def validate_retention_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    max_discount_pct: float,
    *,
    kernel_contract: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """
    Gate stack: ``validate_proposal`` (schema, TTL, RBAC, contract boundaries when provided),
    then deterministic check on ``discount_offered`` vs ``max_discount_pct``.
    """
    verdict, reason = validate_proposal(
        proposal, context, allowed_agents, contract=kernel_contract
    )
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


def dim_validators() -> List:
    """Reserved for ``extra_validators=`` injection; retention gates live in ``validate_retention_proposal``."""
    return []

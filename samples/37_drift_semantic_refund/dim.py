"""
Kernel Space: DIM wrapper for refunds (generic validate_proposal + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from dir_core.data_types import DimReasonCode, ValidationResult, ValidationVerdict
from dir_core.dim import validate_proposal
from dir_core.models import PolicyProposal


def validate_refund_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    max_refund_eur: float,
    *,
    kernel_contract: Optional[Dict[str, Any]] = None,
) -> ValidationResult:
    """
    Gate stack: ``validate_proposal`` (schema, TTL, RBAC, contract boundaries when provided),
    then deterministic check on ``refund_amount_eur`` vs ``max_refund_eur``.
    """
    verdict, reason = validate_proposal(
        proposal, context, allowed_agents, contract=kernel_contract
    )
    if verdict == ValidationVerdict.REJECT:
        return verdict, reason

    raw = proposal.params.get("refund_amount_eur")
    if raw is None:
        return ValidationVerdict.REJECT, "Missing refund_amount_eur in params"
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return ValidationVerdict.REJECT, "Invalid refund_amount_eur type"

    if amount <= 0:
        return ValidationVerdict.REJECT, "Non-positive refund_amount_eur"
    if amount > max_refund_eur + 1e-9:
        return ValidationVerdict.REJECT, f"REFUND_EXCEEDS_CONTRACT max={max_refund_eur}"

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED


def dim_validators() -> List:
    """Reserved for ``custom_validators=`` injection; refund gates live in ``validate_refund_proposal``."""
    return []

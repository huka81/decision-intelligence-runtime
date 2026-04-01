"""
Kernel Space: DIM wrapper for refunds (DIR generic gates + contract ceiling).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Tuple

from dir.dim import validate_proposal
from dir.models import PolicyProposal

ValidationVerdict = Literal["ACCEPT", "REJECT"]
ValidationResult = Tuple[ValidationVerdict, str]


def validate_refund_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    allowed_agents: Optional[List[str]],
    max_refund_eur: float,
) -> ValidationResult:
    """
    Gate stack: dir.dim.validate_proposal, then deterministic contract check on refund_amount_eur.
    DIM does not enforce the 48h semantic rule — only the financial cap.
    """
    verdict, reason = validate_proposal(proposal, context, allowed_agents)
    if verdict == "REJECT":
        return verdict, reason

    raw = proposal.params.get("refund_amount_eur")
    if raw is None:
        return "REJECT", "Missing refund_amount_eur in params"
    try:
        amount = float(raw)
    except (TypeError, ValueError):
        return "REJECT", "Invalid refund_amount_eur type"

    if amount <= 0:
        return "REJECT", "Non-positive refund_amount_eur"
    if amount > max_refund_eur + 1e-9:
        return "REJECT", f"REFUND_EXCEEDS_CONTRACT max={max_refund_eur}"

    return "ACCEPT", "Validation passed"

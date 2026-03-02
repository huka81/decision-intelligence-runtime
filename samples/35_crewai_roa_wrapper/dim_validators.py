"""
35_crewai_roa_wrapper - DIM validation for Claims proposals.

Validates PolicyProposal against:
1. Base DIM (schema, RBAC)
2. Order existence in Context Store
3. Category in allowed_refund_categories
4. Return window (purchase_date + return_window_days)
5. Amount <= max_refund_without_escalation (ACCEPT) or ESCALATE

DIR Alignment: DIR Architectural Pattern §6 (Decision Integrity Module)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from dir import PolicyProposal
from dir.dim import validate_proposal

from contracts import ClaimsContract

ValidationVerdict = str  # "ACCEPT" | "REJECT" | "ESCALATE"


def validate_claims_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    contract: ClaimsContract,
    allowed_agents: Optional[list[str]] = None,
) -> Tuple[ValidationVerdict, str]:
    """
    Validate Claims proposal: base DIM + order + category + return window + amount.

    Validation layers:
    1. Base DIM validation (schema, RBAC)
    2. Order existence in Context Store
    3. Category in allowed_refund_categories
    4. Return window check (within return_window_days)
    5. Amount: <= max -> ACCEPT; > max -> ESCALATE (HITL)

    Args:
        proposal: PolicyProposal with params: order_id, amount_eur, category, reason
        context: Must contain {"orders": {"ord_123": {"purchase_date": "...", "category": "..."}}}
        contract: ClaimsContract with boundaries
        allowed_agents: List of authorized agent IDs

    Returns:
        Tuple of (verdict, reason)
    """
    # Layer 1: Base validation
    base_context = {"state": context.get("state", {})}
    verdict, reason = validate_proposal(
        proposal, base_context, allowed_agents or []
    )
    if verdict == "REJECT":
        return verdict, reason

    # Layer 2: Order existence
    order_id = proposal.params.get("order_id")
    if not order_id:
        return "REJECT", "Missing order_id in proposal params"

    orders = context.get("orders", {})
    if order_id not in orders:
        return "REJECT", f"Order {order_id} not found in Context Store"

    order = orders[order_id]
    category = order.get("category", "UNKNOWN")

    # Layer 3: Category boundary
    if category not in contract.allowed_refund_categories:
        return (
            "REJECT",
            f"Category '{category}' not in allowed_refund_categories "
            f"{contract.allowed_refund_categories}",
        )

    # Layer 4: Return window
    purchase_date_str = order.get("purchase_date")
    if not purchase_date_str:
        return "REJECT", f"Order {order_id} missing purchase_date in Context Store"

    try:
        purchase_date = datetime.fromisoformat(
            purchase_date_str.replace("Z", "+00:00")
        )
        if purchase_date.tzinfo is None:
            purchase_date = purchase_date.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return "REJECT", f"Invalid purchase_date format for order {order_id}"

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=contract.return_window_days
    )
    if purchase_date < cutoff:
        return (
            "REJECT",
            f"Order {order_id} outside return window "
            f"(purchased {purchase_date_str}, limit {contract.return_window_days} days)",
        )

    # Layer 5: Amount - ACCEPT or ESCALATE
    amount = proposal.params.get("amount_eur") or proposal.params.get("amount_pln")
    if amount is None:
        return "REJECT", "Missing amount_eur in proposal params"

    try:
        amount_float = float(amount)
    except (TypeError, ValueError):
        return "REJECT", "amount_eur must be numeric"

    if amount_float <= 0:
        return "REJECT", "amount_eur must be positive"

    if amount_float > contract.max_refund_without_escalation:
        return (
            "ESCALATE",
            f"Amount {amount_float} EUR exceeds "
            f"max_refund_without_escalation ({contract.max_refund_without_escalation} EUR). "
            "Human approval required.",
        )

    return "ACCEPT", "Validation passed"

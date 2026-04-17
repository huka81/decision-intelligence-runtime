"""Claims DIM: ``dir_core.validate_proposal`` plus order, category, window, and amount rules."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from dir_core import PolicyProposal, validate_proposal as dim_validate_proposal
from dir_core.data_types import DimReasonCode, ValidationReason, ValidationVerdict

from contracts import ClaimsContract


def validate_claims_proposal(
    proposal: PolicyProposal,
    context: Dict[str, Any],
    contract: ClaimsContract,
    dim_contract_dict: Dict[str, Any],
    allowed_agents: Optional[List[str]] = None,
) -> Tuple[ValidationVerdict, ValidationReason]:
    agents = allowed_agents if allowed_agents is not None else [contract.agent_id]
    base_ctx: Dict[str, Any] = {"state": context.get("state", {}), "orders": context.get("orders", {})}
    verdict, reason = dim_validate_proposal(
        proposal,
        base_ctx,
        allowed_agents=agents,
        contract=dim_contract_dict,
    )
    if verdict == ValidationVerdict.REJECT:
        return verdict, reason

    order_id = proposal.params.get("order_id")
    if not order_id:
        return ValidationVerdict.REJECT, "Missing order_id in proposal params"

    orders = context.get("orders", {})
    if order_id not in orders:
        return ValidationVerdict.REJECT, f"Order {order_id} not found in Context Store"

    order = orders[order_id]
    category = order.get("category", "UNKNOWN")

    if category not in contract.allowed_refund_categories:
        return (
            ValidationVerdict.REJECT,
            f"Category '{category}' not in allowed_refund_categories "
            f"{contract.allowed_refund_categories}",
        )

    purchase_date_str = order.get("purchase_date")
    if not purchase_date_str:
        return ValidationVerdict.REJECT, f"Order {order_id} missing purchase_date in Context Store"

    try:
        purchase_date = datetime.fromisoformat(str(purchase_date_str).replace("Z", "+00:00"))
        if purchase_date.tzinfo is None:
            purchase_date = purchase_date.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return ValidationVerdict.REJECT, f"Invalid purchase_date format for order {order_id}"

    cutoff = datetime.now(timezone.utc) - timedelta(days=contract.return_window_days)
    if purchase_date < cutoff:
        return (
            ValidationVerdict.REJECT,
            f"Order {order_id} outside return window "
            f"(purchased {purchase_date_str}, limit {contract.return_window_days} days)",
        )

    amount = proposal.params.get("amount_eur") or proposal.params.get("amount_pln")
    if amount is None:
        return ValidationVerdict.REJECT, "Missing amount_eur in proposal params"

    try:
        amount_float = float(amount)
    except (TypeError, ValueError):
        return ValidationVerdict.REJECT, "amount_eur must be numeric"

    if amount_float <= 0:
        return ValidationVerdict.REJECT, "amount_eur must be positive"

    if amount_float > contract.max_refund_without_escalation:
        return (
            ValidationVerdict.ESCALATE,
            f"Amount {amount_float} EUR exceeds "
            f"max_refund_without_escalation ({contract.max_refund_without_escalation} EUR). "
            "Human approval required.",
        )

    return ValidationVerdict.ACCEPT, DimReasonCode.VALIDATION_PASSED

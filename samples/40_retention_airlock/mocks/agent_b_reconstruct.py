"""Deterministic Agent B: reconstruct narrative from proposal JSON only (no original email)."""

from __future__ import annotations

from typing import Any, Dict


def agent_b_reconstruct(proposal: Dict[str, Any]) -> str:
    """
    Mock reconstruction agent — reads ONLY structured proposal fields.
    In production this would be an isolated, one-way LLM call.
    """
    policy_kind = str(proposal.get("policy_kind", ""))
    params = proposal.get("params") if isinstance(proposal.get("params"), dict) else {}
    if policy_kind == "APPLY_DISCOUNT":
        discount = params.get("discount_pct", 0)
        return (
            f"Customer is unhappy with pricing and is being offered "
            f"a retention discount of {discount}%."
        )
    if policy_kind == "CANCEL_SUBSCRIPTION":
        return "Customer subscription cancellation is being processed."
    return f"Proposed action: {policy_kind}."
